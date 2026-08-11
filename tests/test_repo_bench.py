"""Stdlib unittest suite for bin/repo_bench.py (repo-bench kit, T1 foundations).

bin/ is not a package; repo_bench.py is loaded via importlib by absolute path computed from
this file's own location (the house pattern, as in tests/test_cost_report.py).

Everything here is offline and free: throwaway fixture git repos in temp dirs, temp stores,
and injected runners. No model is dispatched, no `claude`/`gh` CLI is invoked, and the real
`benchruns/` store is never written to.
"""

import contextlib
import importlib.util
import inspect
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rb = _load("repo_bench")

RUN_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[0-9a-f]{4}$")


# ---------------------------------------------------------------------------------------------
# fixture helpers


def _git(repo, *args, check=True):
    """Raw git against a fixture repo we own. Identity pinned; branch name never assumed."""
    proc = subprocess.run(
        [
            "git", "-C", str(repo),
            "-c", "user.name=t",
            "-c", "user.email=t@example.com",
            "-c", "init.defaultBranch=fixture",
            "-c", "commit.gpgsign=false",
            *args,
        ],
        capture_output=True,
        text=True,
    )
    if check and proc.returncode != 0:
        raise AssertionError(f"fixture git {args} failed: {proc.stdout}{proc.stderr}")
    return proc.stdout


def build_fixture_repo(root):
    """Two-commit throwaway repo (so parent != HEAD). Returns (head, parent)."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    (root / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    (root / "README.md").write_text("fixture\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "c1: buggy add")
    (root / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (root / "REFERENCE_FIX.md").write_text("this file only exists in the LATER commit\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "c2: fix add (#7)")
    head = _git(root, "rev-parse", "HEAD").strip()
    parent = _git(root, "rev-parse", "HEAD~1").strip()
    return head, parent


def _tree_snapshot(root):
    """Relative path -> content for every non-.git file under root."""
    root = Path(root)
    out = {}
    for path in sorted(root.rglob("*")):
        if ".git" in path.relative_to(root).parts or not path.is_file():
            continue
        out[str(path.relative_to(root))] = path.read_text()
    return out


# ---------------------------------------------------------------------------------------------


class AllowlistTests(unittest.TestCase):
    def test_allowlist_membership_is_exact(self):
        self.assertEqual(
            rb.READ_ONLY_GIT,
            ("archive", "show", "log", "rev-parse", "diff", "ls-tree", "cat-file", "status"),
        )

    def test_write_verbs_are_refused_by_name(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_fixture_repo(repo)
            for verb in ("checkout", "reset", "clean", "push", "commit", "add", "worktree"):
                with self.subTest(verb=verb):
                    with self.assertRaises(ValueError) as ctx:
                        rb.git_target(repo, verb, "-x")
                    msg = str(ctx.exception)
                    self.assertIn(verb, msg)
                    for allowed in rb.READ_ONLY_GIT:
                        self.assertIn(allowed, msg)

    def test_bare_call_with_no_verb_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            rb.git_target("/nonexistent")
        self.assertIn("archive", str(ctx.exception))

    def test_refusal_happens_before_any_runner_call(self):
        calls = []

        def runner(argv):
            calls.append(argv)
            return 0, ""

        with self.assertRaises(ValueError):
            rb.git_target("/nonexistent", "checkout", "HEAD", git_runner=runner)
        self.assertEqual(calls, [])

    def test_allowed_verb_reaches_the_runner_with_dash_C(self):
        calls = []

        def runner(argv):
            calls.append(argv)
            return 0, "deadbeef\n"

        rc, out = rb.git_target("/some/target", "rev-parse", "HEAD", git_runner=runner)
        self.assertEqual((rc, out), (0, "deadbeef\n"))
        self.assertEqual(calls, [["git", "-C", "/some/target", "rev-parse", "HEAD"]])

    def test_git_sandbox_has_no_allowlist_and_pins_identity(self):
        calls = []

        def runner(argv):
            calls.append(argv)
            return 0, ""

        rb.git_sandbox("/some/sandbox", "commit", "-m", "x", git_runner=runner)
        argv = calls[0]
        self.assertEqual(argv[:3], ["git", "-C", "/some/sandbox"])
        self.assertIn("user.name=repo-bench", argv)
        self.assertEqual(argv[-3:], ["commit", "-m", "x"])


class SandboxTests(unittest.TestCase):
    def test_sandbox_tree_matches_the_archived_commit(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            head, parent = build_fixture_repo(repo)
            info = rb.make_sandbox(repo, parent, td / "sb")

            self.assertEqual(info["base_commit"], parent)
            self.assertEqual(info["path"], str(td / "sb"))

            expected_names = sorted(
                n for n in _git(repo, "ls-tree", "-r", "--name-only", parent).splitlines() if n
            )
            got = _tree_snapshot(td / "sb")
            self.assertEqual(sorted(got), expected_names)
            for name in expected_names:
                self.assertEqual(got[name], _git(repo, "show", f"{parent}:{name}"))

            # the LATER commit's file must not be reachable in the sandbox
            self.assertNotIn("REFERENCE_FIX.md", got)
            self.assertFalse((td / "sb" / "REFERENCE_FIX.md").exists())
            self.assertNotEqual(parent, head)

    def test_sandbox_has_exactly_one_commit_and_no_target_history(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            head, parent = build_fixture_repo(repo)
            info = rb.make_sandbox(repo, parent, td / "sb")

            log = _git(td / "sb", "log", "--oneline").strip().splitlines()
            self.assertEqual(len(log), 1, f"sandbox history leaked: {log}")
            self.assertEqual(
                _git(td / "sb", "rev-list", "--count", "HEAD").strip(), "1"
            )
            self.assertEqual(_git(td / "sb", "rev-parse", "HEAD").strip(), info["init_commit"])

            # no target object is reachable: neither the base commit nor the fix commit
            for sha in (head, parent):
                proc = subprocess.run(
                    ["git", "-C", str(td / "sb"), "cat-file", "-e", f"{sha}^{{commit}}"],
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(proc.returncode, 0, f"target commit {sha} present in sandbox")
            self.assertEqual(_git(td / "sb", "remote").strip(), "")

    def test_target_repo_is_unchanged_after_sandboxing(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            _, parent = build_fixture_repo(repo)

            before = {
                "head": _git(repo, "rev-parse", "HEAD"),
                "refs": _git(repo, "show-ref"),
                "log": _git(repo, "log", "--oneline"),
                "status": _git(repo, "status", "--porcelain"),
                "tree": _tree_snapshot(repo),
            }
            rb.make_sandbox(repo, parent, td / "sb")
            after = {
                "head": _git(repo, "rev-parse", "HEAD"),
                "refs": _git(repo, "show-ref"),
                "log": _git(repo, "log", "--oneline"),
                "status": _git(repo, "status", "--porcelain"),
                "tree": _tree_snapshot(repo),
            }
            self.assertEqual(before, after)
            self.assertEqual(after["status"], "")

    def test_make_sandbox_touches_git_only_through_the_two_choke_points(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            _, parent = build_fixture_repo(repo)

            target_calls, sandbox_calls, runner_calls = [], [], []
            orig_target = rb.git_target
            orig_sandbox = rb.git_sandbox
            orig_runner = rb.default_git_runner

            def spy_target(r, *args, **kw):
                target_calls.append(args)
                return orig_target(r, *args, **kw)

            def spy_sandbox(s, *args, **kw):
                sandbox_calls.append(args)
                return orig_sandbox(s, *args, **kw)

            def spy_runner(argv):
                runner_calls.append(argv)
                return orig_runner(argv)

            with mock.patch.object(rb, "git_target", spy_target), \
                    mock.patch.object(rb, "git_sandbox", spy_sandbox), \
                    mock.patch.object(rb, "default_git_runner", spy_runner):
                rb.make_sandbox(repo, parent, td / "sb")

            # every git invocation is accounted for by one of the two choke points
            self.assertEqual(len(runner_calls), len(target_calls) + len(sandbox_calls))
            self.assertTrue(target_calls)
            for args in target_calls:
                self.assertIn(args[0], rb.READ_ONLY_GIT)
            # and every argv aimed at the TARGET path carries an allowlisted verb
            for argv in runner_calls:
                self.assertEqual(argv[0], "git")
                if argv[2] == str(repo):
                    self.assertIn(argv[3], rb.READ_ONLY_GIT)
                else:
                    self.assertEqual(argv[2], str(td / "sb"))

    def test_missing_target_raises_file_not_found(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FileNotFoundError):
                rb.make_sandbox(Path(td) / "nope", "HEAD", Path(td) / "sb")

    def test_bad_commit_raises_value_error(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_fixture_repo(repo)
            with self.assertRaises(ValueError):
                rb.make_sandbox(repo, "0" * 40, td / "sb")


class CapturePatchTests(unittest.TestCase):
    def _sandbox(self, td):
        repo = td / "target"
        _, parent = build_fixture_repo(repo)
        return rb.make_sandbox(repo, parent, td / "sb")

    def test_uncommitted_work_is_captured(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            info = self._sandbox(td)
            sb = Path(info["path"])
            (sb / "brand_new.py").write_text("value = 1\n")
            (sb / "calc.py").write_text("def add(a, b):\n    return a + b\n")

            patch = rb.capture_patch(sb)
            self.assertIn("brand_new.py", patch)
            self.assertIn("value = 1", patch)
            self.assertIn("calc.py", patch)
            self.assertIn("return a + b", patch)

    def test_committed_work_is_captured(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            info = self._sandbox(td)
            sb = Path(info["path"])
            (sb / "brand_new.py").write_text("value = 1\n")
            _git(sb, "add", "-A")
            _git(sb, "commit", "-q", "-m", "candidate commit")

            patch = rb.capture_patch(sb)
            self.assertIn("brand_new.py", patch)
            self.assertIn("value = 1", patch)

    def test_committed_then_edited_further_is_all_captured(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            info = self._sandbox(td)
            sb = Path(info["path"])
            (sb / "brand_new.py").write_text("value = 1\n")
            _git(sb, "add", "-A")
            _git(sb, "commit", "-q", "-m", "candidate commit")
            (sb / "later.py").write_text("value = 2\n")

            patch = rb.capture_patch(sb)
            self.assertIn("brand_new.py", patch)
            self.assertIn("later.py", patch)

    def test_no_work_yields_an_empty_patch(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            info = self._sandbox(td)
            self.assertEqual(rb.capture_patch(info["path"]).strip(), "")

    def test_explicit_init_commit_is_honoured(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            info = self._sandbox(td)
            sb = Path(info["path"])
            (sb / "brand_new.py").write_text("value = 1\n")
            patch = rb.capture_patch(sb, init_commit=info["init_commit"])
            self.assertIn("brand_new.py", patch)
            self.assertEqual(
                rb.sandbox_init_commit(sb), info["init_commit"]
            )


class RunStoreTests(unittest.TestCase):
    def test_new_run_dir_shape(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "benchruns"
            run_id, run_path = rb.new_run_dir(store)

            self.assertRegex(run_id, RUN_ID_RE)
            self.assertEqual(run_path, store / run_id)
            for sub in ("tasks", "dispatches", "work"):
                self.assertTrue((run_path / sub).is_dir(), sub)

            meta = json.loads((run_path / "meta.json").read_text())
            self.assertEqual(meta["store_schema_version"], rb.STORE_SCHEMA_VERSION)
            self.assertEqual(meta["run_id"], run_id)
            self.assertTrue(meta["created_at"].endswith("+00:00"))
            self.assertTrue(meta["created_at"].startswith(run_id[:10]))

    def test_two_runs_get_distinct_dirs(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "benchruns"
            first, _ = rb.new_run_dir(store)
            second, _ = rb.new_run_dir(store)
            self.assertNotEqual(first, second)
            rows, notes = rb.list_runs(store)
            self.assertEqual(sorted(r["run_id"] for r in rows), sorted([first, second]))
            self.assertEqual(notes, [])

    def test_list_runs_missing_dir(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "benchruns"
            rows, notes = rb.list_runs(missing)
            self.assertEqual(rows, [])
            self.assertEqual(len(notes), 1)
            self.assertIn("no benchruns store at", notes[0])
            self.assertIn(str(missing), notes[0])

    def test_list_runs_store_path_is_a_file(self):
        with tempfile.TemporaryDirectory() as td:
            bogus = Path(td) / "benchruns"
            bogus.write_text("not a store\n")
            rows, notes = rb.list_runs(bogus)
            self.assertEqual(rows, [])
            self.assertTrue(any("not a directory" in n for n in notes))

    def test_list_runs_empty_store(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "benchruns"
            store.mkdir()
            rows, notes = rb.list_runs(store)
            self.assertEqual(rows, [])
            self.assertTrue(any("empty" in n for n in notes))

    def test_list_runs_tolerance_matrix(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "benchruns"
            good_id, _ = rb.new_run_dir(store)

            (store / "stray.txt").write_text("rogue\n")
            (store / "2020-01-01-aaaa").mkdir()  # run dir with no meta.json
            broken = store / "2020-01-02-bbbb"
            broken.mkdir()
            (broken / "meta.json").write_text("{not json at all")
            listy = store / "2020-01-03-cccc"
            listy.mkdir()
            (listy / "meta.json").write_text("[1, 2, 3]")

            rows, notes = rb.list_runs(store)
            self.assertEqual([r["run_id"] for r in rows], [good_id])
            self.assertEqual(rows[0]["path"], str(store / good_id))
            joined = " | ".join(notes)
            self.assertIn("stray.txt", joined)
            self.assertIn("2020-01-01-aaaa", joined)
            self.assertIn("2020-01-02-bbbb", joined)
            self.assertIn("2020-01-03-cccc", joined)


class CliTests(unittest.TestCase):
    # T4 implemented `plan`/`run` (PlanCliTests/RunCliTests), T8 implemented `verdict`
    # (VerdictCliTests), and T9 implements `apply` (ApplyCliTests) -- every subcommand this
    # module names now has real coverage; there is no later-task stub left to assert against.

    def test_plan_and_run_require_repo_and_models(self):
        for name in ("plan", "run"):
            with self.subTest(name=name):
                err = io.StringIO()
                with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
                    rb.main([name])
                self.assertEqual(ctx.exception.code, 2)
                self.assertIn("--repo", err.getvalue())
                self.assertIn("--models", err.getvalue())

    def test_no_subcommand_prints_help_and_exits_2(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as ctx:
            rb.main([])
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("usage", out.getvalue().lower())

    def test_list_on_a_temp_store(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "benchruns"
            run_id, _ = rb.new_run_dir(store)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rb.main(["list", "--store-dir", str(store)])
            text = out.getvalue()
            self.assertIn(run_id, text)
            self.assertIn(str(store), text)

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rb.main(["list", "--store-dir", str(store), "--json"])
            payload = json.loads(out.getvalue())
            self.assertEqual([r["run_id"] for r in payload["runs"]], [run_id])

    def test_list_on_a_missing_store_is_friendly(self):
        with tempfile.TemporaryDirectory() as td:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rb.main(["list", "--store-dir", str(Path(td) / "nope")])
            self.assertIn("no benchruns store at", out.getvalue())

    def test_demo_proves_the_foundations_and_writes_no_store(self):
        store = rb.DEFAULT_STORE_DIR
        before = sorted(p.name for p in store.iterdir()) if store.is_dir() else None

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rb.main(["demo"])
        text = out.getvalue()

        after = sorted(p.name for p in store.iterdir()) if store.is_dir() else None
        self.assertEqual(before, after, "demo wrote into the real benchruns store")

        self.assertIn("sandbox", text.lower())
        self.assertIn("rev-list --count HEAD = 1", text)
        self.assertIn("present in sandbox = False", text)
        self.assertIn("new_uncommitted.py in patch = True", text)
        self.assertIn("new_committed.py in patch = True", text)
        self.assertNotIn("DIRTY", text)


def build_issue_fixture_repo(root):
    """History with: a fix commit ('fixes #7') touching source AND a tests/ file; a fix
    commit ('closes #9') touching no tests; a plain non-fix commit. Returns a dict of shas.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")

    (root / "m.py").write_text("def f():\n    return 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "start: initial version")
    c0 = _git(root, "rev-parse", "HEAD").strip()

    (root / "README.md").write_text("just docs, nothing fixed here\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "docs: unrelated tidy-up")
    c_nonfix = _git(root, "rev-parse", "HEAD").strip()

    (root / "other.py").write_text("def g():\n    return 'ungoverned'\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "closes #9: add g() but add no test for it")
    c_notest = _git(root, "rev-parse", "HEAD").strip()

    (root / "m.py").write_text("def f():\n    return 2\n")
    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_m.py").write_text("import m\nassert m.f() == 2\n")
    _git(root, "add", "-A")
    _git(
        root, "commit", "-q", "-m",
        "fixes #7: f() should return 2\n\nThe old value was wrong; see the issue for repro.",
    )
    c_fix = _git(root, "rev-parse", "HEAD").strip()

    return {
        "start": c0,
        "nonfix": c_nonfix,
        "notest": c_notest,
        "fix": c_fix,
    }


class IssueReplayMinerTests(unittest.TestCase):
    def test_pair_extraction_correct_base_and_nonempty_patch(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            shas = build_issue_fixture_repo(repo)
            tasks, notes = rb.mine_issue_tasks(repo, gh_runner=None)

            by_id = {t["task_id"]: t for t in tasks}
            fix_task = by_id[f"issue-7-{shas['fix'][:7]}"]
            self.assertEqual(fix_task["fix_commit"], shas["fix"])
            self.assertEqual(fix_task["base_commit"], shas["notest"])
            self.assertEqual(fix_task["mode"], "issue-replay")
            self.assertEqual(fix_task["issue"], 7)
            self.assertTrue(fix_task["reference_patch"].strip())
            self.assertIn("return 2", fix_task["reference_patch"])

    def test_oracle_tests_available_true_false_split(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            shas = build_issue_fixture_repo(repo)
            tasks, notes = rb.mine_issue_tasks(repo, gh_runner=None)

            by_issue = {t["issue"]: t for t in tasks}
            self.assertTrue(by_issue[7]["oracle_tests_available"])
            self.assertEqual(list(by_issue[7]["test_blobs"]), ["tests/test_m.py"])
            self.assertFalse(by_issue[9]["oracle_tests_available"])
            self.assertEqual(by_issue[9]["test_blobs"], {})

    def test_test_blob_content_equals_fixed_file_at_fix_commit(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            shas = build_issue_fixture_repo(repo)
            tasks, notes = rb.mine_issue_tasks(repo, gh_runner=None)

            by_issue = {t["issue"]: t for t in tasks}
            expected = _git(repo, "show", f"{shas['fix']}:tests/test_m.py")
            self.assertEqual(by_issue[7]["test_blobs"]["tests/test_m.py"], expected)

    def test_non_fix_commit_yields_no_task(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            shas = build_issue_fixture_repo(repo)
            tasks, notes = rb.mine_issue_tasks(repo, gh_runner=None)
            self.assertEqual(sorted(t["issue"] for t in tasks), [7, 9])
            self.assertNotIn(shas["nonfix"], [t["fix_commit"] for t in tasks])

    def test_leak_rule_prompt_excludes_reference_and_blob_content(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_issue_fixture_repo(repo)
            tasks, notes = rb.mine_issue_tasks(repo, gh_runner=None)

            for task in tasks:
                prompt = rb.build_prompt(task)
                for line in task["reference_patch"].splitlines():
                    stripped = line.strip()
                    if len(stripped) > 10:
                        self.assertNotIn(stripped, prompt)
                for blob in task["test_blobs"].values():
                    for line in blob.splitlines():
                        stripped = line.strip()
                        if stripped:
                            self.assertNotIn(stripped, prompt)

    def test_limit_is_respected(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_issue_fixture_repo(repo)
            tasks, notes = rb.mine_issue_tasks(repo, limit=1, gh_runner=None)
            self.assertEqual(len(tasks), 1)
            # newest-first: the #7 fix commit is HEAD, so it wins the single slot.
            self.assertEqual(tasks[0]["issue"], 7)

    def test_root_commit_skip_is_noted(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            root = Path(repo)
            root.mkdir(parents=True, exist_ok=True)
            _git(root, "init", "-q")
            (root / "m.py").write_text("def f():\n    return 1\n")
            _git(root, "add", "-A")
            _git(root, "commit", "-q", "-m", "fixes #1: root commit itself is the fix")

            tasks, notes = rb.mine_issue_tasks(repo, gh_runner=None)
            self.assertEqual(tasks, [])
            self.assertTrue(any("root commit" in n for n in notes))

    def test_use_gh_false_never_calls_injected_gh_runner(self):
        def exploding_runner(argv):
            raise AssertionError(f"gh_runner must never be called when use_gh=False: {argv}")

        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_issue_fixture_repo(repo)
            tasks, notes = rb.mine_issue_tasks(repo, gh_runner=exploding_runner)  # use_gh defaults False
            self.assertTrue(tasks)
            for t in tasks:
                self.assertEqual(t["statement_source"], "commit-message")
                self.assertIn(
                    "statement from commit message (weaker than issue text)", t["labels"]
                )

    def test_statement_source_and_weak_label_from_commit_message(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_issue_fixture_repo(repo)
            tasks, notes = rb.mine_issue_tasks(repo, gh_runner=None)
            by_issue = {t["issue"]: t for t in tasks}
            self.assertEqual(by_issue[7]["statement_source"], "commit-message")
            self.assertIn("f() should return 2", by_issue[7]["statement"])
            self.assertIn("repro", by_issue[7]["statement"])

    def test_use_gh_true_with_runner_is_used_for_statement(self):
        calls = []

        def gh_runner(argv):
            calls.append(argv)
            return 0, json.dumps({"title": "f() returns the wrong value", "body": "repro steps"})

        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_issue_fixture_repo(repo)
            tasks, notes = rb.mine_issue_tasks(repo, gh_runner=gh_runner, use_gh=True)

            self.assertTrue(calls)
            by_issue = {t["issue"]: t for t in tasks}
            self.assertEqual(by_issue[7]["statement_source"], "issue")
            self.assertIn("f() returns the wrong value", by_issue[7]["statement"])
            self.assertNotIn(
                "statement from commit message (weaker than issue text)", by_issue[7]["labels"]
            )

    def test_size_profile_uses_pricing_task_profile_keys(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_issue_fixture_repo(repo)
            tasks, notes = rb.mine_issue_tasks(repo, gh_runner=None)
            valid = rb._pricing_task_profile_keys()
            for t in tasks:
                self.assertIn(t["size_profile"], valid)

    def test_git_target_is_the_only_history_access(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_issue_fixture_repo(repo)
            calls = []
            orig = rb.git_target

            def spy(r, *args, **kw):
                calls.append(args)
                return orig(r, *args, **kw)

            with mock.patch.object(rb, "git_target", spy):
                rb.mine_issue_tasks(repo, gh_runner=None)
            self.assertTrue(calls)
            for args in calls:
                self.assertIn(args[0], rb.READ_ONLY_GIT)


class GhFlagDegradationTests(unittest.TestCase):
    """T14 -- `--with-gh` honest degradation. Every runner here is a plain stub function;
    the ABSOLUTE FENCE is that no test in this file may invoke a real `gh` (GUARDRAILS).
    Each failure mode must fall back to the EXISTING commit-message statement/label, plus a
    note naming what specifically failed -- never an empty or invented statement.
    """

    def _fix_task(self, tasks):
        by_issue = {t["issue"]: t for t in tasks}
        return by_issue[7]

    def _assert_honest_fallback(self, task, expected_note_fragment):
        self.assertEqual(task["statement_source"], "commit-message")
        self.assertIn(
            "statement from commit message (weaker than issue text)", task["labels"]
        )
        self.assertTrue(task["statement"], "fallback statement must never be empty")
        self.assertIn("f() should return 2", task["statement"])
        self.assertTrue(
            any(expected_note_fragment in n for n in task["notes"]),
            task["notes"],
        )

    def test_gh_not_on_path(self):
        def gh_runner(argv):
            return 127, "gh: command not found -- is the GitHub CLI installed and on PATH?"

        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_issue_fixture_repo(repo)
            tasks, _notes = rb.mine_issue_tasks(repo, gh_runner=gh_runner, use_gh=True)
            self._assert_honest_fallback(self._fix_task(tasks), "not found on PATH")

    def test_gh_not_authenticated(self):
        def gh_runner(argv):
            return 1, (
                "To get started with GitHub CLI, please run:  gh auth login\n"
                "You are not logged into any GitHub hosts."
            )

        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_issue_fixture_repo(repo)
            tasks, _notes = rb.mine_issue_tasks(repo, gh_runner=gh_runner, use_gh=True)
            self._assert_honest_fallback(self._fix_task(tasks), "not authenticated")

    def test_issue_number_is_actually_a_pull_request(self):
        # T16: `gh issue view` used to be assumed to ERROR on a PR number (the old stub
        # below simulated that) -- real `gh` does not; it happily returns rc=0 and the PR's
        # body. `gh api repos/<owner>/<name>/issues/<N>` returns the SAME success (rc=0) but
        # as raw JSON carrying a `pull_request` key, which is what the discriminator checks.
        def gh_runner(argv):
            return 0, json.dumps({
                "title": "Fix bool narrowing for numeric literal patterns",
                "body": "## Summary\n- Preserve `Literal[False]` ...",
                "pull_request": {"url": "https://api.github.com/repos/o/n/pulls/7"},
            })

        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_issue_fixture_repo(repo)
            tasks, _notes = rb.mine_issue_tasks(repo, gh_runner=gh_runner, use_gh=True)
            task = self._fix_task(tasks)
            self._assert_honest_fallback(task, "is a pull request, not an issue")
            # THE DEFECT: neither the PR title nor its body may leak into the statement.
            self.assertNotIn("bool narrowing", task["statement"])
            self.assertNotIn("Literal[False]", task["statement"])

    def test_issue_not_found_private_or_rate_limited(self):
        def gh_runner(argv):
            return 1, "GraphQL: Could not resolve to an issue with the number 7. (issue)"

        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_issue_fixture_repo(repo)
            tasks, _notes = rb.mine_issue_tasks(repo, gh_runner=gh_runner, use_gh=True)
            self._assert_honest_fallback(self._fix_task(tasks), "issue not found")

    def test_rate_limited(self):
        def gh_runner(argv):
            return 1, "API rate limit exceeded for installation ID 123."

        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_issue_fixture_repo(repo)
            tasks, _notes = rb.mine_issue_tasks(repo, gh_runner=gh_runner, use_gh=True)
            self._assert_honest_fallback(self._fix_task(tasks), "rate-limited")

    def test_unparseable_json_response(self):
        def gh_runner(argv):
            return 0, "not json at all {{{"

        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_issue_fixture_repo(repo)
            tasks, _notes = rb.mine_issue_tasks(repo, gh_runner=gh_runner, use_gh=True)
            self._assert_honest_fallback(self._fix_task(tasks), "unparseable")

    def test_unclassified_failure_still_falls_back_with_the_rc(self):
        def gh_runner(argv):
            return 1, "some brand-new gh error text nothing here matches"

        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_issue_fixture_repo(repo)
            tasks, _notes = rb.mine_issue_tasks(repo, gh_runner=gh_runner, use_gh=True)
            self._assert_honest_fallback(self._fix_task(tasks), "rc=1")


class GhEnrichmentPlanCardTests(unittest.TestCase):
    """T14 -- the plan card must report the enrichment ratio, but ONLY when enrichment was
    actually attempted (`use_gh=True`); the default (`use_gh=False`) stays label-free."""

    def test_enrichment_label_reports_the_ratio_when_with_gh_is_set(self):
        def gh_runner(argv):
            if any("issues/7" in a for a in argv):
                return 0, json.dumps({"title": "real issue title", "body": "real repro"})
            return 1, "GraphQL: Could not resolve to an issue with that number. (issue)"

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            card = rb.build_plan(
                repo, ["fake-haiku-1"], pricing=FIXTURE_PRICING, scratch_dir=td / "scratch",
                use_gh=True, gh_runner=gh_runner,
            )
            self.assertEqual(len(card["tasks"]), 2)
            label = [l for l in card["labels"] if l.startswith("gh enrichment:")]
            self.assertEqual(label, ["gh enrichment: 1/2 task(s) used real issue text"])

    def test_enrichment_label_counts_pull_requests_separately(self):
        """T16 -- a PR body must never inflate the ratio, and the label must say how many of
        the misses were pull requests rather than leaving that undifferentiated."""
        def gh_runner(argv):
            if any("issues/7" in a for a in argv):
                return 0, json.dumps({"title": "real issue title", "body": "real repro"})
            # issue 9 resolves to a PR
            return 0, json.dumps({
                "title": "add g()", "body": "adds g() to fix the underlying bug",
                "pull_request": {"url": "https://api.github.com/repos/o/n/pulls/9"},
            })

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            card = rb.build_plan(
                repo, ["fake-haiku-1"], pricing=FIXTURE_PRICING, scratch_dir=td / "scratch",
                use_gh=True, gh_runner=gh_runner,
            )
            self.assertEqual(len(card["tasks"]), 2)
            label = [l for l in card["labels"] if l.startswith("gh enrichment:")]
            self.assertEqual(
                label,
                ["gh enrichment: 1/2 task(s) used real issue text (1 were pull requests)"],
            )

    def test_no_enrichment_label_when_with_gh_is_unset(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            card = rb.build_plan(
                repo, ["fake-haiku-1"], pricing=FIXTURE_PRICING, scratch_dir=td / "scratch",
            )
            self.assertFalse([l for l in card["labels"] if l.startswith("gh enrichment:")])

    def test_a_general_mode_card_carries_no_enrichment_label_and_spends_no_gh_call(self):
        """T17R/F6 — the ratio is about `issue_tasks`, and general mode REPLACES the task set.
        A general-mode card used to report an enrichment ratio about tasks that are not in the
        run, having spent one real `gh` API call on each of them first."""
        calls = []

        def gh_runner(argv):
            calls.append(argv)
            return 0, json.dumps({"title": "real issue title", "body": "real repro"})

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_general_and_issues_fixture_repo(repo)
            card = rb.build_plan(
                repo, ["fake-haiku-1"], mode="general", limit=1, test_cmd="general-tests",
                pricing=FIXTURE_PRICING, scratch_dir=td / "scratch",
                test_runner=_classify_test_runner, use_gh=True, gh_runner=gh_runner,
            )
        self.assertEqual(card["mode"], "general")
        self.assertTrue(card["tasks"], "the fixture mined no general task to prove this on")
        self.assertFalse(
            [l for l in card["labels"] if l.startswith("gh enrichment:")],
            "a general-mode card reported an enrichment ratio about discarded issue tasks",
        )
        self.assertEqual(
            calls, [], "a forced general-mode plan spent a gh call per discarded issue task"
        )

    def test_an_issue_replay_card_still_carries_the_label(self):
        """The other half of F6: the fix must not silence the label where it is true."""
        def gh_runner(argv):
            return 0, json.dumps({"title": "real issue title", "body": "real repro"})

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_general_and_issues_fixture_repo(repo)
            card = rb.build_plan(
                repo, ["fake-haiku-1"], mode="issue-replay", pricing=FIXTURE_PRICING,
                scratch_dir=td / "scratch", use_gh=True, gh_runner=gh_runner,
            )
        self.assertTrue([l for l in card["labels"] if l.startswith("gh enrichment:")])


def build_general_and_issues_fixture_repo(root):
    """A repo the general miner CAN work on that also carries issue-fix commits — the only
    shape in which F6's mislabel is visible (issue tasks mined, then discarded)."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    (root / "m.py").write_text("def f():\n    return 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "start: initial version")

    (root / "m.py").write_text("def f():\n    return 2\n")
    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_m.py").write_text("assert f() == 2\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixes #7: f() should return 2")

    (root / "classify.py").write_text(
        "def classify(x):\n"
        "    if x >= 10:\n"
        '        return "big"\n'
        '    return "small"\n'
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "add classify with a mutatable comparison")
    return _git(root, "rev-parse", "HEAD").strip()


def _classify_test_runner(cmd, cwd):
    """Red exactly when the comparison in `classify.py` has been mutated."""
    source = Path(cwd) / "classify.py"
    if not source.exists():
        return 1, "FAIL: classify.py is missing"
    return (1, "FAIL: classify(10) is no longer big") if "x > 10" in source.read_text() \
        else (0, "OK")


def build_no_issue_fixture_repo(root):
    """Two plain commits, neither `fix(es)/close(s)/resolve(s) #N` nor a `(#N)` squash-merge
    suffix -- `mine_issue_tasks` mines ZERO tasks from this repo. Used only for T14's CLI
    wiring tests: even if a real `gh` runner were reachable, there is nothing here to call it
    for."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    (root / "a.py").write_text("x = 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "initial commit, no issue reference at all")
    (root / "a.py").write_text("x = 2\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "tweak a value, still no issue reference")
    return root


class GhFlagCliTests(unittest.TestCase):
    """T14 -- `--with-gh` reaches the CLI on both `plan` and `run`, and is a no-op unless
    set. GUARDRAILS' absolute fence forbids this test FILE from ever naming the real runtime
    `gh` runner or invoking a real `gh` -- so wiring is proven by spying on `build_plan`
    itself (never a real subprocess) with a fixture repo that mines NO issue-referencing
    commits, so even a real runner passed through would never actually be called."""

    def test_plan_help_lists_the_flag(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            rb.main(["plan", "--help"])
        self.assertIn("--with-gh", out.getvalue())

    def test_run_help_lists_the_flag(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            rb.main(["run", "--help"])
        self.assertIn("--with-gh", out.getvalue())

    def _build_plan_spy(self, calls):
        orig = rb.build_plan

        def spy(*args, **kwargs):
            calls.append(kwargs)
            return orig(*args, **kwargs)

        return spy

    def test_plan_cli_without_the_flag_passes_use_gh_false_and_no_runner(self):
        calls = []
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_no_issue_fixture_repo(repo)  # nothing to enrich
            out = io.StringIO()
            with mock.patch.object(rb, "build_plan", self._build_plan_spy(calls)):
                with contextlib.redirect_stdout(out):
                    rb.main(["plan", "--repo", str(repo), "--models", "haiku,sonnet", "--json"])
            self.assertTrue(calls)
            self.assertIs(calls[-1]["use_gh"], False)
            self.assertIsNone(calls[-1]["gh_runner"])

    def test_plan_cli_with_the_flag_passes_use_gh_true_and_a_runner(self):
        calls = []
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_no_issue_fixture_repo(repo)  # nothing to enrich
            out = io.StringIO()
            with mock.patch.object(rb, "build_plan", self._build_plan_spy(calls)):
                with contextlib.redirect_stdout(out):
                    rb.main([
                        "plan", "--repo", str(repo), "--models", "haiku,sonnet",
                        "--with-gh", "--gh-repo", "owner/name", "--json",
                    ])
            self.assertTrue(calls)
            self.assertIs(calls[-1]["use_gh"], True)
            self.assertIsNotNone(calls[-1]["gh_runner"])
            self.assertTrue(callable(calls[-1]["gh_runner"]))
            self.assertEqual(calls[-1]["gh_repo"], "owner/name")

    def test_run_cli_without_the_flag_passes_use_gh_false_and_no_runner(self):
        calls = []
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_no_issue_fixture_repo(repo)  # nothing to enrich
            store = td / "store"
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(rb, "build_plan", self._build_plan_spy(calls)):
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                        self.assertRaises(SystemExit) as ctx:
                    rb.main([
                        "run", "--repo", str(repo), "--models", "haiku",
                        "--store-dir", str(store),
                    ])
            # missing --live/--max-usd still refuses (D1) -- unaffected by the flag either way
            self.assertEqual(ctx.exception.code, 2)
            self.assertTrue(calls)
            self.assertIs(calls[-1]["use_gh"], False)
            self.assertIsNone(calls[-1]["gh_runner"])

    def test_run_cli_with_the_flag_passes_use_gh_true_and_a_runner(self):
        calls = []
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_no_issue_fixture_repo(repo)  # nothing to enrich
            store = td / "store"
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(rb, "build_plan", self._build_plan_spy(calls)):
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                        self.assertRaises(SystemExit) as ctx:
                    rb.main([
                        "run", "--repo", str(repo), "--models", "haiku",
                        "--store-dir", str(store), "--with-gh", "--gh-repo", "owner/name",
                    ])
            self.assertEqual(ctx.exception.code, 2)
            self.assertTrue(calls)
            self.assertIs(calls[-1]["use_gh"], True)
            self.assertIsNotNone(calls[-1]["gh_runner"])
            self.assertTrue(callable(calls[-1]["gh_runner"]))
            self.assertEqual(calls[-1]["gh_repo"], "owner/name")


class GhRunnerDefaultsTests(unittest.TestCase):
    """T14 -- the library must NEVER default to a real `gh`. The stronger claim (the
    runtime runner is constructed ONLY on the CLI `--with-gh` path, never wired as any
    parameter default) is checked by this task's Verify block itself, deliberately OUTSIDE
    this test file -- GUARDRAILS forbids this file from naming that runner at all."""

    def test_gh_runner_param_defaults_stay_none(self):
        for fn in (rb.mine_issue_tasks, rb.build_plan):
            default = inspect.signature(fn).parameters["gh_runner"].default
            self.assertIsNone(default, f"{fn.__name__} defaults gh_runner to {default!r}")

    def test_use_gh_param_defaults_stay_false(self):
        for fn in (rb.mine_issue_tasks, rb.build_plan):
            default = inspect.signature(fn).parameters["use_gh"].default
            self.assertIs(default, False, f"{fn.__name__} defaults use_gh to {default!r}")


class GhRepoFlagTests(unittest.TestCase):
    """T15 -- `gh issue view <N>` with no `--repo` resolves the repository from the CURRENT
    WORKING DIRECTORY, not from the target being benchmarked, so every lookup silently
    queried the wrong project. T16 replaced the `gh issue view --repo <X>` argv shape with
    `gh api repos/<X>/issues/<N>` (`--repo` folded into the URL path), so these assertions
    check the path segment instead of a `--repo` flag; the underlying guarantee (an unset
    `--gh-repo` must never silently query the wrong project) is unchanged. Every runner here
    is a plain stub function; no test in this file may invoke a real `gh` (GUARDRAILS)."""

    def test_gh_argv_carries_repo_when_gh_repo_is_set(self):
        calls = []

        def gh_runner(argv):
            calls.append(argv)
            return 0, json.dumps({"title": "f() returns the wrong value", "body": "repro"})

        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_issue_fixture_repo(repo)
            rb.mine_issue_tasks(
                repo, gh_runner=gh_runner, use_gh=True, gh_repo="octocat/hello-world",
            )
            self.assertTrue(calls)
            for argv in calls:
                self.assertIn("gh", argv)
                self.assertIn("api", argv)
                self.assertTrue(
                    any("repos/octocat/hello-world/issues/" in a for a in argv), argv
                )

    def test_gh_argv_has_no_repo_flag_when_gh_repo_unset(self):
        """Library-level call with no `gh_repo` stays permissive (T14/T15): it uses the
        `{owner}/{repo}` placeholder, which `gh api` resolves from the current working
        directory -- the CLI gate (not this function) is what refuses an unset --gh-repo."""
        calls = []

        def gh_runner(argv):
            calls.append(argv)
            return 0, json.dumps({"title": "t", "body": "b"})

        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_issue_fixture_repo(repo)
            rb.mine_issue_tasks(repo, gh_runner=gh_runner, use_gh=True)
            self.assertTrue(calls)
            for argv in calls:
                self.assertTrue(
                    any("repos/{owner}/{repo}/issues/" in a for a in argv), argv
                )

    def test_with_gh_without_gh_repo_refuses_and_dispatches_nothing(self):
        # `build_plan` is where `gh_runner_arg` would be constructed and passed down -- if
        # it is never called, no `gh` runner is ever built or invoked, real or otherwise.
        calls = []
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_issue_fixture_repo(repo)
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(rb, "build_plan", self._spy(calls)):
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                        self.assertRaises(SystemExit) as ctx:
                    rb.main([
                        "plan", "--repo", str(repo), "--models", "haiku", "--with-gh",
                    ])
            self.assertEqual(ctx.exception.code, 2)
            self.assertIn("--gh-repo", err.getvalue())
            self.assertFalse(calls, "build_plan must not be reached without --gh-repo")

    def test_malformed_gh_repo_refuses(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_issue_fixture_repo(repo)
            for bad in ("https://github.com/o/n", "o/n/extra", "just-a-name", ""):
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                        self.assertRaises(SystemExit) as ctx:
                    rb.main([
                        "plan", "--repo", str(repo), "--models", "haiku",
                        "--with-gh", "--gh-repo", bad,
                    ])
                self.assertEqual(ctx.exception.code, 2, f"{bad!r} should have refused")

    def test_gh_repo_without_with_gh_is_accepted_and_unused(self):
        calls = []
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_no_issue_fixture_repo(repo)
            out = io.StringIO()
            with mock.patch.object(rb, "build_plan", self._spy(calls)):
                with contextlib.redirect_stdout(out):
                    rb.main([
                        "plan", "--repo", str(repo), "--models", "haiku",
                        "--gh-repo", "octocat/hello-world", "--json",
                    ])
            self.assertTrue(calls)
            self.assertIs(calls[-1]["use_gh"], False)
            self.assertIsNone(calls[-1]["gh_runner"])
            self.assertEqual(calls[-1]["gh_repo"], "octocat/hello-world")

    def test_both_set_with_stubbed_success_counts_toward_enrichment(self):
        calls = []

        def gh_runner(argv):
            calls.append(argv)
            return 0, json.dumps({"title": "f() returns the wrong value", "body": "repro"})

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            card = rb.build_plan(
                repo, ["fake-haiku-1"], pricing=FIXTURE_PRICING, scratch_dir=td / "scratch",
                use_gh=True, gh_runner=gh_runner, gh_repo="octocat/hello-world",
            )
            self.assertTrue(calls)
            for argv in calls:
                self.assertTrue(
                    any("repos/octocat/hello-world/issues/" in a for a in argv), argv
                )
            label = [l for l in card["labels"] if l.startswith("gh enrichment:")]
            self.assertEqual(label, ["gh enrichment: 2/2 task(s) used real issue text"])

    @staticmethod
    def _spy(calls):
        orig = rb.build_plan

        def spy(*args, **kwargs):
            calls.append(kwargs)
            return orig(*args, **kwargs)

        return spy


def build_exclude_subject_fixture_repo(root):
    """A real fix ('fixes #7') plus a squash-merged dependency bump ('Bump ... (#9)') whose
    subject also satisfies `ISSUE_REF_RE`'s squash-merge branch. T13: the bump must be
    excludable by subject without touching `ISSUE_REF_RE` itself. Returns a dict of shas.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")

    (root / "m.py").write_text("x = 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "start")

    (root / "m.py").write_text("x = 2\n")
    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_m.py").write_text("import m\nassert m.x == 2\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixes #7: real fix")
    c_fix = _git(root, "rev-parse", "HEAD").strip()

    (root / "pkg.json").write_text("{}\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "Bump brace-expansion from 5.0.6 to 5.0.8 (#99)")
    c_bump = _git(root, "rev-parse", "HEAD").strip()

    return {"fix": c_fix, "bump": c_bump}


class ExcludeSubjectMinerTests(unittest.TestCase):
    """T13 -- opt-in `exclude_subject` on `mine_issue_tasks`/`build_plan`. Absent means
    today's behavior, exactly (PLAN's compatibility posture); exclusion is opt-in, visible in
    a note naming the dropped commit, and summarised on the plan card's `labels`."""

    def test_default_mines_both_the_fix_and_the_bump(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_exclude_subject_fixture_repo(repo)
            tasks, notes = rb.mine_issue_tasks(repo, gh_runner=None)
            self.assertEqual(len(tasks), 2, [t["task_id"] for t in tasks])
            self.assertFalse([n for n in notes if "excluded by --exclude-subject" in n])

    def test_exclude_subject_drops_the_bump_and_notes_it(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_exclude_subject_fixture_repo(repo)
            tasks, notes = rb.mine_issue_tasks(
                repo, gh_runner=None, exclude_subject=(r"^Bump ",)
            )
            self.assertEqual(len(tasks), 1, [t["task_id"] for t in tasks])
            self.assertEqual(tasks[0]["issue"], 7)
            excluded = [n for n in notes if "excluded by --exclude-subject" in n]
            self.assertTrue(excluded, notes)
            self.assertIn("Bump brace-expansion", excluded[0])

    def test_exclude_subject_is_case_insensitive_and_uses_re_search(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_exclude_subject_fixture_repo(repo)
            tasks, notes = rb.mine_issue_tasks(
                repo, gh_runner=None, exclude_subject=(r"bump",)
            )
            self.assertEqual(len(tasks), 1, [t["task_id"] for t in tasks])
            self.assertEqual(tasks[0]["issue"], 7)

    def test_invalid_regex_is_refused_with_a_plain_sentence(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_exclude_subject_fixture_repo(repo)
            with self.assertRaises(ValueError) as ctx:
                rb.mine_issue_tasks(repo, gh_runner=None, exclude_subject=(r"[unterminated",))
            message = str(ctx.exception)
            self.assertNotIn("Traceback", message)
            self.assertIn("--exclude-subject", message)

    def test_build_plan_promotes_a_summary_label_when_exclusion_fires(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_exclude_subject_fixture_repo(repo)
            card = rb.build_plan(
                repo, ["fake-haiku-1"], pricing=FIXTURE_PRICING, scratch_dir=td / "scratch",
                exclude_subject=(r"^Bump ",),
            )
            self.assertEqual(len(card["tasks"]), 1)
            summary = [l for l in card["labels"] if "excluded by --exclude-subject" in l]
            self.assertEqual(summary, ["1 commit(s) excluded by --exclude-subject"])

    def test_build_plan_default_carries_no_exclusion_label(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_exclude_subject_fixture_repo(repo)
            card = rb.build_plan(
                repo, ["fake-haiku-1"], pricing=FIXTURE_PRICING, scratch_dir=td / "scratch",
            )
            self.assertEqual(len(card["tasks"]), 2)
            self.assertFalse([l for l in card["labels"] if "excluded by --exclude-subject" in l])

    def test_exclude_count_does_not_inflate_past_the_limit(self):
        """T19/F8 -- `--exclude-subject` still checks BEFORE the `len(tasks) >= limit` break
        (unreordered), so the walk still passes over the trailing bumps to find the end of the
        log. What must change is the REPORTED count: those trailing exclusions were never
        needed to mine the one task the run actually planned, so they must not appear in
        `notes` or inflate `excluded_count` on the plan card."""
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            c_fix = build_exclude_subject_limit_fixture_repo(repo)
            tasks, notes = rb.mine_issue_tasks(
                repo, limit=1, gh_runner=None, exclude_subject=(r"^Bump ",)
            )
            self.assertEqual(len(tasks), 1, [t["task_id"] for t in tasks])
            self.assertEqual(tasks[0]["fix_commit"], c_fix)
            excluded = [n for n in notes if "excluded by --exclude-subject" in n]
            self.assertEqual(
                excluded, [],
                "commits walked over only to find the end of the log after the quota was "
                "already met were still counted as excluded",
            )

    def test_build_plan_card_carries_no_exclusion_label_once_the_quota_is_met(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_exclude_subject_limit_fixture_repo(repo)
            card = rb.build_plan(
                repo, ["fake-haiku-1"], pricing=FIXTURE_PRICING, scratch_dir=td / "scratch",
                limit=1, exclude_subject=(r"^Bump ",),
            )
            self.assertEqual(len(card["tasks"]), 1)
            self.assertFalse(
                [l for l in card["labels"] if "excluded by --exclude-subject" in l],
                card["labels"],
            )

    def test_cli_exclude_subject_is_repeatable_and_wired_into_plan(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_exclude_subject_fixture_repo(repo)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rb.main([
                    "plan", "--repo", str(repo), "--models", "haiku,sonnet",
                    "--exclude-subject", r"^Bump ", "--exclude-subject", r"^Never matches$",
                    "--json",
                ])
            card = json.loads(out.getvalue())
            self.assertEqual(len(card["tasks"]), 1)
            self.assertTrue(
                any("excluded by --exclude-subject" in l for l in card["labels"]), card["labels"]
            )


def build_exclude_subject_limit_fixture_repo(root):
    """T19/F8 -- the fix commit is the NEWEST commit; three excludable bumps are OLDER (`git
    log` walks newest-first). With `--limit 1`, mining reaches its quota on the very first
    commit examined, and the three trailing bumps are only walked over to find the end of the
    log -- they were never needed to build the one-task set actually mined, so they must not
    inflate the reported exclusion count. Returns the fix commit's sha."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")

    (root / "m.py").write_text("x = 0\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "start")

    for n in range(1, 4):
        (root / f"dep{n}.json").write_text("{}\n")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", f"Bump dep{n} from 1.0 to 2.0 (#{90 + n})")

    (root / "m.py").write_text("x = 1\n")
    tests_dir = root / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "test_m.py").write_text("import m\nassert m.x == 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixes #7: real fix")
    return _git(root, "rev-parse", "HEAD").strip()


def build_general_fixture_repo(root):
    """Single-commit fixture with two mutation-operator candidate lines:

    - `classify()` uses `>=`; flipping it to `>` changes `classify(10)`'s result -- RED.
    - `unused()` uses `==`, but the (stub) test never calls `unused()` -- flipping it is a
      GREEN, non-discriminating mutation that must be discarded.

    Returns the single commit's sha.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    (root / "calc.py").write_text(
        "def classify(x):\n"
        "    if x >= 10:\n"
        "        return \"big\"\n"
        "    return \"small\"\n"
        "\n"
        "\n"
        "def unused(x):\n"
        "    if x == 5:\n"
        "        return \"five\"\n"
        "    return \"not five\"\n"
    )
    (root / "README.md").write_text("fixture\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "c1: classify + unused")
    return _git(root, "rev-parse", "HEAD").strip()


def _classify_test_runner(cmd, cwd):
    """STUB `test_runner` emulating a tiny real test script: import `calc.py` fresh from
    `cwd` and assert `classify(10) == 'big'`. rc 1 (red/fail) if the mutation broke that
    assertion, rc 0 (green/pass) otherwise -- no real subprocess, no `cmd` interpretation.

    Bytecode caching is disabled for the duration: an uncontrolled `__pycache__/*.pyc`
    dropped into the sandbox would become an untracked file in the "mutated" commit and
    break the reference-patch round trip below.
    """
    spec = importlib.util.spec_from_file_location("repo_bench_calc_fixture", Path(cwd) / "calc.py")
    mod = importlib.util.module_from_spec(spec)
    prev = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(mod)
        assert mod.classify(10) == "big"
    except Exception as e:  # noqa: BLE001 - any failure of the tiny fixture test is a red
        return 1, f"FAIL: {e}"
    finally:
        sys.dont_write_bytecode = prev
    return 0, "OK"


class GeneralModeMinerTests(unittest.TestCase):
    def test_missing_test_cmd_raises_value_error(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            head = build_general_fixture_repo(repo)
            with self.assertRaises(ValueError) as ctx:
                rb.mine_general_tasks(repo, head, test_cmd=None)
            self.assertIn("test command", str(ctx.exception))

            with self.assertRaises(ValueError):
                rb.mine_general_tasks(repo, head, test_cmd="")

    def test_red_validated_admission_and_green_discard_with_note(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            head = build_general_fixture_repo(repo)
            scratch = td / "scratch"

            tasks, notes = rb.mine_general_tasks(
                repo, head, test_cmd="run-tests", test_runner=_classify_test_runner,
                scratch_dir=scratch,
            )

            # exactly one candidate mutation is discriminating (the >= site); the == site
            # (in unused(), which the stub test never calls) is green and discarded.
            self.assertEqual(len(tasks), 1)
            task = tasks[0]
            self.assertEqual(task["mode"], "general")
            self.assertEqual(task["task_id"], "mut-1-calc")
            self.assertTrue(task["oracle_tests_available"])
            self.assertIn("synthetic mutation-repair task", task["labels"])
            self.assertTrue(task["reference_patch"].strip())

            self.assertTrue(
                any("discarded" in n and "green" in n for n in notes),
                notes,
            )

    def test_statement_never_names_the_mutated_file_or_the_operator(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            head = build_general_fixture_repo(repo)

            tasks, notes = rb.mine_general_tasks(
                repo, head, test_cmd="run-tests", test_runner=_classify_test_runner,
                scratch_dir=td / "scratch",
            )
            self.assertTrue(tasks)
            for task in tasks:
                # `subject` is as candidate-facing as `statement` -- build_prompt falls back
                # to it and T7's judge prompt reads it -- so it is held to the same rule.
                for field in ("statement", "subject"):
                    text = task[field]
                    self.assertTrue(text.strip(), field)
                    self.assertNotIn("calc", text.lower(), field)
                    self.assertNotIn(".py", text, field)
                    for op_name, pattern, replacement in rb.MUTATION_OPERATORS:
                        self.assertNotIn(op_name, text, field)
                        self.assertNotIn(pattern, text, field)
                        self.assertNotIn(replacement, text, field)
                # the prompt built from it is equally silent about the bug's location
                prompt = rb.build_prompt(task)
                self.assertNotIn("calc", prompt.lower())
                # ... and so is the prompt when only `subject` is available (the fallback)
                fallback = rb.build_prompt({"subject": task["subject"]})
                self.assertNotIn("calc", fallback.lower())

    def test_reference_patch_reverses_the_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            head = build_general_fixture_repo(repo)
            scratch = td / "scratch"
            original_calc = _git(repo, "show", f"{head}:calc.py")

            tasks, notes = rb.mine_general_tasks(
                repo, head, test_cmd="run-tests", test_runner=_classify_test_runner,
                scratch_dir=scratch,
            )
            self.assertEqual(len(tasks), 1)
            task = tasks[0]

            # T5R/F1: the mining scratch sandboxes no longer survive their own red check --
            # under `run` they live at `<run-dir>/work/site-N`, one `../` from a candidate's
            # cwd, and their init commit is the UNMUTATED source. So the round trip is proved
            # on a replica this test builds itself, exactly as a candidate's sandbox is built.
            self.assertFalse(
                list(scratch.glob("site-*")),
                "a mining scratch sandbox survived its red check (F1 — that is the answer, "
                "readable one directory up from the candidate's cwd)",
            )

            info = rb.make_sandbox(repo, head, td / "replica")
            replica = Path(info["path"])
            self.assertEqual((replica / "calc.py").read_text(), original_calc)

            setup_file = td / "setup.patch"
            setup_file.write_text(task["setup_patch"])
            _git(replica, "apply", str(setup_file))
            mutated_on_disk = (replica / "calc.py").read_text()
            self.assertIn("x > 10", mutated_on_disk)
            self.assertNotEqual(mutated_on_disk, original_calc)

            patch_file = td / "ref.patch"
            patch_file.write_text(task["reference_patch"])
            proc = subprocess.run(
                ["git", "-C", str(replica), "apply", str(patch_file)],
                capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

            restored = (replica / "calc.py").read_text()
            self.assertEqual(restored, original_calc)

    def test_bounded_scan_stops_after_limit_times_four_sites(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            root = repo
            root.mkdir(parents=True, exist_ok=True)
            _git(root, "init", "-q")
            # 10 independent >= mutation sites, ALL green under this always-green stub, so
            # nothing gets admitted and the scan must stop itself on the examined-count bound
            # (limit * 4) rather than running through all 10.
            body = "".join(f"def f{i}(x):\n    return x >= {i}\n\n" for i in range(10))
            (root / "many.py").write_text(body)
            _git(root, "add", "-A")
            _git(root, "commit", "-q", "-m", "many sites")
            head = _git(root, "rev-parse", "HEAD").strip()

            def always_green(cmd, cwd):
                return 0, "always green"

            tasks, notes = rb.mine_general_tasks(
                repo, head, limit=2, test_cmd="run-tests", test_runner=always_green,
                scratch_dir=td / "scratch",
            )
            self.assertEqual(tasks, [])
            discard_notes = [n for n in notes if "discarded" in n]
            self.assertEqual(len(discard_notes), 2 * 4)


class ChooseModeTests(unittest.TestCase):
    def test_min_evidence_tasks_is_five(self):
        self.assertEqual(rb.MIN_EVIDENCE_TASKS, 5)

    def test_below_floor_falls_back_to_general(self):
        mode, reason = rb.choose_mode([{"task_id": "a"}, {"task_id": "b"}], rb.MIN_EVIDENCE_TASKS)
        self.assertEqual(mode, "general")
        self.assertTrue(reason)
        self.assertIsInstance(reason, str)

    def test_at_or_above_floor_prefers_issue_replay(self):
        issue_tasks = [{"task_id": str(i)} for i in range(rb.MIN_EVIDENCE_TASKS)]
        mode, reason = rb.choose_mode(issue_tasks, rb.MIN_EVIDENCE_TASKS)
        self.assertEqual(mode, "issue-replay")
        self.assertTrue(reason)

        mode, reason = rb.choose_mode(issue_tasks + [{"task_id": "extra"}], rb.MIN_EVIDENCE_TASKS)
        self.assertEqual(mode, "issue-replay")

    def test_zero_issue_tasks_is_general(self):
        mode, reason = rb.choose_mode([], rb.MIN_EVIDENCE_TASKS)
        self.assertEqual(mode, "general")


class MutationOperatorTableTests(unittest.TestCase):
    def test_shape_is_name_pattern_replacement_triples(self):
        for entry in rb.MUTATION_OPERATORS:
            self.assertEqual(len(entry), 3)
            name, pattern, replacement = entry
            self.assertIsInstance(name, str)
            self.assertIsInstance(pattern, str)
            self.assertIsInstance(replacement, str)
            self.assertNotEqual(pattern, replacement)

    def test_expected_operators_present(self):
        pairs = {(pattern, replacement) for _n, pattern, replacement in rb.MUTATION_OPERATORS}
        self.assertIn(("==", "!="), pairs)
        self.assertIn(("<=", "<"), pairs)
        self.assertIn((">=", ">"), pairs)
        self.assertIn(("+ 1", "- 1"), pairs)
        self.assertIn(("True", "False"), pairs)
        self.assertIn(("true", "false"), pairs)
        self.assertIn((" and ", " or "), pairs)
        self.assertIn(("&&", "||"), pairs)


class ReuseTests(unittest.TestCase):
    def test_run_id_comes_from_claude_execute(self):
        ce = rb._ce()
        self.assertTrue(hasattr(ce, "generate_run_id"))
        with mock.patch.object(ce, "generate_run_id", return_value="2020-05-05-beef") as gen:
            with tempfile.TemporaryDirectory() as td:
                run_id, run_path = rb.new_run_dir(Path(td) / "benchruns")
        self.assertEqual(run_id, "2020-05-05-beef")
        self.assertEqual(run_path.name, "2020-05-05-beef")
        self.assertTrue(gen.called)

    def test_plugin_root_and_default_store(self):
        self.assertTrue((rb.PLUGIN_ROOT / "bin" / "repo_bench.py").exists())
        self.assertEqual(rb.DEFAULT_STORE_DIR, rb.PLUGIN_ROOT / "benchruns")


# ---------------------------------------------------------------------------------------------
# T3R — Phase 1 remediation: schema parity, miner robustness, the red candidate sandbox.


def build_parity_fixture_repo(root):
    """ONE repo both miners can work on: a `fixes #5` pair in its history AND a live `>=`
    mutation site in the source at HEAD. Returns (head, fix_sha)."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    (root / "calc.py").write_text(
        "def classify(x):\n"
        "    if x >= 10:\n"
        "        return \"big\"\n"
        "    return \"small\"\n"
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "c1: classify")

    (root / "calc.py").write_text(
        "def classify(x):\n"
        "    if x >= 10:\n"
        "        return \"big\"\n"
        "    return \"small\"\n"
        "\n"
        "# boundary behaviour is deliberate\n"
    )
    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_calc.py").write_text("import calc\nassert calc.classify(10) == \"big\"\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixes #5: classify(10) belongs to the big bucket")
    fix = _git(root, "rev-parse", "HEAD").strip()
    return fix, fix


def _ge_marker_runner(cmd, cwd):
    """STUB `test_runner`: RED exactly when calc.py's `>=` site has been flipped to `>`.

    A genuine red signal read from the sandbox it is handed -- no subprocess, no
    interpretation of `cmd`, no model, no network.
    """
    text = (Path(cwd) / "calc.py").read_text()
    return (1, "FAIL: classify(10) is no longer big") if "x > 10" in text else (0, "OK")


def _mine_one_of_each(td, repo):
    """(issue_task, general_task) mined from the same parity fixture repo."""
    head, _ = build_parity_fixture_repo(repo)
    issue_tasks, _ = rb.mine_issue_tasks(repo, gh_runner=None)
    general_tasks, _ = rb.mine_general_tasks(
        repo, head, test_cmd="run-tests", test_runner=_ge_marker_runner,
        scratch_dir=Path(td) / "scratch",
    )
    assert issue_tasks and general_tasks, (issue_tasks, general_tasks)
    return issue_tasks[0], general_tasks[0]


class SchemaParityTests(unittest.TestCase):
    """F1 — a general record that omits `issue`/`fix_commit`/`subject` is a KeyError landing
    in a consumer AFTER dispatches have been paid for."""

    def test_both_miners_emit_identical_key_sets(self):
        with tempfile.TemporaryDirectory() as td:
            issue_task, general_task = _mine_one_of_each(td, Path(td) / "target")
            self.assertEqual(set(issue_task), set(general_task))
            self.assertEqual(set(issue_task), set(rb.TASK_RECORD_KEYS))

    def test_general_record_fills_the_issue_only_fields_with_none(self):
        with tempfile.TemporaryDirectory() as td:
            _issue_task, general_task = _mine_one_of_each(td, Path(td) / "target")
            self.assertIsNone(general_task["issue"])
            self.assertIsNone(general_task["fix_commit"])
            self.assertEqual(general_task["subject"], rb.GENERAL_SUBJECT)
            self.assertTrue(general_task["subject"].strip())

    def test_issue_record_carries_setup_patch_none(self):
        with tempfile.TemporaryDirectory() as td:
            issue_task, _general_task = _mine_one_of_each(td, Path(td) / "target")
            self.assertIsNone(issue_task["setup_patch"])
            self.assertEqual(issue_task["issue"], 5)

    def test_finalize_task_refuses_a_drifting_key_set(self):
        with tempfile.TemporaryDirectory() as td:
            issue_task, _ = _mine_one_of_each(td, Path(td) / "target")

            missing = dict(issue_task)
            missing.pop("subject")
            with self.assertRaises(ValueError) as ctx:
                rb._finalize_task(missing)
            self.assertIn("subject", str(ctx.exception))

            extra = dict(issue_task)
            extra["surprise"] = 1
            with self.assertRaises(ValueError) as ctx:
                rb._finalize_task(extra)
            self.assertIn("surprise", str(ctx.exception))


class SetupPatchTests(unittest.TestCase):
    """F3 — without `setup_patch` the candidate's sandbox (built fresh off `base_commit`) is
    GREEN, so general mode measures nothing while appearing to work."""

    def test_setup_patch_turns_a_fresh_candidate_sandbox_red(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            head, _ = build_parity_fixture_repo(repo)
            tasks, _notes = rb.mine_general_tasks(
                repo, head, test_cmd="run-tests", test_runner=_ge_marker_runner,
                scratch_dir=td / "scratch",
            )
            self.assertEqual(len(tasks), 1)
            task = tasks[0]
            self.assertTrue(task["setup_patch"].strip(), "general task carries no setup_patch")

            # a candidate's sandbox, exactly as T5 will build it: fresh off `base_commit`
            info = rb.make_sandbox(repo, task["base_commit"], td / "candidate")
            sandbox = Path(info["path"])

            rc_before, _ = _ge_marker_runner("run-tests", str(sandbox))
            self.assertEqual(rc_before, 0, "fresh sandbox should be GREEN before setup_patch")

            patch_file = td / "setup.patch"
            patch_file.write_text(task["setup_patch"])
            _git(sandbox, "apply", str(patch_file))

            rc_after, _ = _ge_marker_runner("run-tests", str(sandbox))
            self.assertNotEqual(
                rc_after, 0,
                "setup_patch did not make the candidate's sandbox RED -- the task statement "
                "('the test suite fails') would be a lie",
            )

    def test_setup_patch_and_reference_patch_are_inverses(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            head, _ = build_parity_fixture_repo(repo)
            tasks, _notes = rb.mine_general_tasks(
                repo, head, test_cmd="run-tests", test_runner=_ge_marker_runner,
                scratch_dir=td / "scratch",
            )
            task = tasks[0]
            original = _git(repo, "show", f"{head}:calc.py")

            info = rb.make_sandbox(repo, task["base_commit"], td / "candidate")
            sandbox = Path(info["path"])
            self.assertEqual((sandbox / "calc.py").read_text(), original)

            setup_file = td / "setup.patch"
            setup_file.write_text(task["setup_patch"])
            _git(sandbox, "apply", str(setup_file))
            self.assertNotEqual((sandbox / "calc.py").read_text(), original)

            ref_file = td / "ref.patch"
            ref_file.write_text(task["reference_patch"])
            _git(sandbox, "apply", str(ref_file))
            self.assertEqual((sandbox / "calc.py").read_text(), original)

    def test_setup_patch_is_documented_as_a_dispatch_precondition(self):
        source = (BIN_DIR / "repo_bench.py").read_text()
        docstring = rb.__doc__ or ""
        self.assertIn("setup_patch", docstring)
        self.assertIn("SETUP-PATCH LAW", docstring)
        # and again as a key comment at the point of construction
        self.assertIn("SETUP-PATCH LAW", source.split(docstring, 1)[-1])


class StatementSourceVocabularyTests(unittest.TestCase):
    """F6 — T3 introduced a third value; T8's renderer must be written against all three."""

    def test_vocabulary_is_pinned_and_complete(self):
        self.assertEqual(rb.STATEMENT_SOURCES, ("issue", "commit-message", "generated"))
        self.assertEqual(len(rb.STATEMENT_SOURCES), 3)

    def test_every_emitted_record_uses_a_member(self):
        with tempfile.TemporaryDirectory() as td:
            issue_task, general_task = _mine_one_of_each(td, Path(td) / "target")
            for task in (issue_task, general_task):
                self.assertIn(task["statement_source"], rb.STATEMENT_SOURCES)
            self.assertEqual(general_task["statement_source"], "generated")
            self.assertEqual(issue_task["statement_source"], "commit-message")

    def test_gh_enrichment_uses_the_third_member(self):
        def gh_runner(argv):
            return 0, json.dumps({"title": "classify(10) misfiles", "body": "repro"})

        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_parity_fixture_repo(repo)
            tasks, _ = rb.mine_issue_tasks(repo, gh_runner=gh_runner, use_gh=True)
            self.assertEqual(tasks[0]["statement_source"], "issue")
            self.assertIn(tasks[0]["statement_source"], rb.STATEMENT_SOURCES)

    def test_finalize_task_refuses_an_unpinned_source(self):
        with tempfile.TemporaryDirectory() as td:
            issue_task, _ = _mine_one_of_each(td, Path(td) / "target")
            rogue = dict(issue_task, statement_source="vibes")
            with self.assertRaises(ValueError) as ctx:
                rb._finalize_task(rogue)
            self.assertIn("vibes", str(ctx.exception))
            self.assertIn("STATEMENT_SOURCES", str(ctx.exception))


def build_deleted_test_fixture_repo(root):
    """History: a good `fixes #2` pair, then a `fixes #3` commit that DELETES a test file.

    `git diff --name-only` reports the deleted path, but `git show <sha>:<deleted path>`
    exits 128 -- which used to abort the whole pass and lose every already-mined pair.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    (root / "m.py").write_text("def f():\n    return 1\n")
    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_old.py").write_text("import m\nassert m.f() is not None\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "start")

    (root / "m.py").write_text("def f():\n    return 2\n")
    (tests_dir / "test_m.py").write_text("import m\nassert m.f() == 2\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixes #2: f() should return 2")
    good = _git(root, "rev-parse", "HEAD").strip()

    (tests_dir / "test_old.py").unlink()
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixes #3: drop the obsolete test")
    deleting = _git(root, "rev-parse", "HEAD").strip()
    return {"good": good, "deleting": deleting}


class DeletedTestBlobTests(unittest.TestCase):
    """F2 — a fix commit that deletes a test file must not abort the whole mining pass."""

    def test_deleted_test_path_is_skipped_with_a_note_and_the_good_pair_survives(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            shas = build_deleted_test_fixture_repo(repo)

            tasks, notes = rb.mine_issue_tasks(repo, gh_runner=None)
            by_issue = {t["issue"]: t for t in tasks}

            self.assertIn(2, by_issue, f"the good pair was lost; notes={notes}")
            good = by_issue[2]
            self.assertEqual(good["fix_commit"], shas["good"])
            self.assertTrue(good["oracle_tests_available"])
            self.assertIn("tests/test_m.py", good["test_blobs"])

            joined = " | ".join(notes)
            self.assertIn("tests/test_old.py", joined)
            self.assertTrue(any("skipped" in n for n in notes), notes)

    def test_the_deleting_commit_still_yields_a_task_without_a_phantom_oracle(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_deleted_test_fixture_repo(repo)
            tasks, _notes = rb.mine_issue_tasks(repo, gh_runner=None)
            by_issue = {t["issue"]: t for t in tasks}

            self.assertIn(3, by_issue)
            deleting = by_issue[3]
            self.assertEqual(deleting["test_blobs"], {})
            self.assertFalse(
                deleting["oracle_tests_available"],
                "a test path with no readable blob cannot grade anything",
            )
            self.assertTrue(
                any("tests/test_old.py" in n for n in deleting["notes"]), deleting["notes"]
            )


#: Latin-1 bytes that are valid text but NOT valid UTF-8 -- and carry no NUL, so git treats
#: the file as text and puts the raw bytes in a diff.
LATIN1_LINE = "café naïve résumé\n".encode("latin-1")


def build_latin1_fixture_repo(root):
    """A repo carrying a latin-1 source file whose suffix is NOT in `BINARY_SUFFIXES`,
    plus a good ASCII `fixes #2` pair and a `fixes #3` commit that touches the latin-1
    file (so the issue miner's diff read hits it too)."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    (root / "calc.py").write_text(
        "def classify(x):\n"
        "    if x >= 10:\n"
        "        return \"big\"\n"
        "    return \"small\"\n"
    )
    (root / "legacy.txt").write_bytes(LATIN1_LINE)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "start")

    (root / "calc.py").write_text(
        "def classify(x):\n"
        "    if x >= 10:\n"
        "        return \"big\"\n"
        "    return \"small\"\n"
        "\n"
        "# boundary behaviour is deliberate\n"
    )
    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_calc.py").write_text("import calc\nassert calc.classify(10) == \"big\"\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixes #2: classify(10) belongs to the big bucket")

    (root / "legacy.txt").write_bytes(LATIN1_LINE + LATIN1_LINE)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixes #3: refresh the legacy note")
    return _git(root, "rev-parse", "HEAD").strip()


class NonUtf8FileTests(unittest.TestCase):
    """F4 — `default_git_runner` decodes strictly, so one latin-1 file used to abort either
    miner with an opaque exit 2. It degrades with a note now; the runner is NOT loosened to
    `errors="replace"` (that would silently corrupt the test blobs written into grade
    copies at T6)."""

    def test_default_git_runner_still_decodes_strictly(self):
        # Behavioural, not a grep: undecodable bytes must RAISE, so every caller degrades
        # deliberately. A global errors="replace" would hand back silently corrupted text --
        # and those bytes become the test blobs written into grade copies at T6.
        with self.assertRaises(UnicodeDecodeError):
            rb.default_git_runner(
                [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\xe9\\n')"]
            )
        self.assertNotIn("errors=", inspect.getsource(rb.default_git_runner))

    def test_the_raw_seam_really_raises_on_latin1(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            head = build_latin1_fixture_repo(repo)
            with self.assertRaises(UnicodeDecodeError):
                rb.git_target(repo, "show", f"{head}:legacy.txt")
            rc, out, undecodable = rb._git_target_text(repo, "show", f"{head}:legacy.txt")
            self.assertTrue(undecodable)
            self.assertIsNone(rc)
            self.assertEqual(out, "")

    def test_issue_miner_completes_and_notes_the_skip(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_latin1_fixture_repo(repo)

            tasks, notes = rb.mine_issue_tasks(repo, gh_runner=None)
            by_issue = {t["issue"]: t for t in tasks}
            self.assertIn(2, by_issue, f"the ASCII pair was lost; notes={notes}")
            self.assertTrue(by_issue[2]["oracle_tests_available"])

            joined = " | ".join(notes)
            self.assertIn("legacy.txt", joined)
            self.assertIn("UTF-8", joined)

    def test_general_miner_completes_and_notes_the_skip(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            head = build_latin1_fixture_repo(repo)

            tasks, notes = rb.mine_general_tasks(
                repo, head, test_cmd="run-tests", test_runner=_ge_marker_runner,
                scratch_dir=td / "scratch",
            )
            self.assertTrue(tasks, f"the mutable ASCII file yielded nothing; notes={notes}")
            joined = " | ".join(notes)
            self.assertIn("legacy.txt", joined)
            self.assertIn("UTF-8", joined)


class PricingReuseTests(unittest.TestCase):
    """F7 — `data/pricing.json` is the single numeric source of truth and `cost_report`
    already owns the one path to it."""

    def test_module_never_re_derives_the_pricing_path(self):
        source = (BIN_DIR / "repo_bench.py").read_text()
        self.assertNotIn('PLUGIN_ROOT / "data"', source)
        self.assertNotIn("PLUGIN_ROOT / 'data'", source)
        self.assertNotIn("pricing.json", source.replace("data/pricing.json", ""))

    def test_profile_keys_come_from_the_cost_report_loader(self):
        cr = rb._cr()
        self.assertEqual(cr.PRICING_PATH, rb.PLUGIN_ROOT / "data" / "pricing.json")
        with mock.patch.object(
            cr, "load_pricing", return_value={"task_profiles": {"fake-a": {}, "fake-b": {}}}
        ) as loader:
            self.assertEqual(rb._pricing_task_profile_keys(), {"fake-a", "fake-b"})
        self.assertTrue(loader.called)

    def test_real_pricing_covers_every_size_label(self):
        keys = rb._pricing_task_profile_keys()
        for _threshold, label in rb.SIZE_THRESHOLDS:
            self.assertIn(label, keys)
        self.assertIn("L", keys)

    def test_both_miners_validate_size_profile_labels(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            head, _ = build_parity_fixture_repo(repo)

            with mock.patch.object(rb, "_pricing_task_profile_keys", return_value={"XS"}):
                with self.assertRaises(ValueError) as ctx:
                    rb.mine_issue_tasks(repo, gh_runner=None)
                self.assertIn("task_profiles", str(ctx.exception))

                with self.assertRaises(ValueError) as ctx:
                    rb.mine_general_tasks(
                        repo, head, test_cmd="run-tests", test_runner=_ge_marker_runner,
                        scratch_dir=td / "scratch",
                    )
                self.assertIn("task_profiles", str(ctx.exception))


class DemoFixtureGitTests(unittest.TestCase):
    """F10 — the demo's fixture builder must not point `git_sandbox` at something it then
    hands to `make_sandbox` as a target."""

    def test_fixture_builder_never_calls_git_sandbox(self):
        calls = []
        orig = rb.git_sandbox

        def spy(sandbox, *args, **kw):
            calls.append((str(sandbox), args))
            return orig(sandbox, *args, **kw)

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "fixture"
            with mock.patch.object(rb, "git_sandbox", spy):
                head, parent = rb._build_demo_repo(root)
            self.assertEqual(calls, [], "demo fixture repo built through git_sandbox")
            self.assertNotEqual(head, parent)
            self.assertTrue((root / "SECRET_FIX.md").exists())

    def test_fixture_git_pins_identity_and_has_no_allowlist(self):
        calls = []

        def runner(argv):
            calls.append(argv)
            return 0, ""

        rb._fixture_git("/some/fixture", "commit", "-m", "x", git_runner=runner)
        argv = calls[0]
        self.assertEqual(argv[:3], ["git", "-C", "/some/fixture"])
        self.assertIn("user.name=repo-bench", argv)
        self.assertEqual(argv[-3:], ["commit", "-m", "x"])


class DefaultTestRunnerTests(unittest.TestCase):
    """F11a — `default_test_runner`'s string/`shell=True` path (what a user types into
    `--test-cmd`) had no coverage. Exercised here with a harmless stdlib command only: no
    model, no network, no `claude`/`gh`, nothing written outside a temp dir."""

    def test_string_command_goes_through_a_shell_and_runs_in_cwd(self):
        with tempfile.TemporaryDirectory() as td:
            cmd = (
                shlex.quote(sys.executable)
                + " -c 'import os, sys; sys.stdout.write(os.getcwd()); sys.exit(3)'"
            )
            rc, out = rb.default_test_runner(cmd, td)
            self.assertEqual(rc, 3)
            self.assertEqual(Path(out.strip()).resolve(), Path(td).resolve())

    def test_string_command_shell_operators_are_interpreted(self):
        with tempfile.TemporaryDirectory() as td:
            py = shlex.quote(sys.executable)
            # `&&` only means anything if a shell parsed it -- the proof that shell=True
            # is on the string path.
            rc, _out = rb.default_test_runner(
                f"{py} -c 'pass' && {py} -c 'import sys; sys.exit(5)'", td
            )
            self.assertEqual(rc, 5)

    def test_string_command_success_is_rc_zero_with_output(self):
        with tempfile.TemporaryDirectory() as td:
            rc, out = rb.default_test_runner(
                shlex.quote(sys.executable) + " -c 'print(\"suite ok\")'", td
            )
            self.assertEqual(rc, 0)
            self.assertIn("suite ok", out)

    def test_list_command_runs_without_a_shell(self):
        with tempfile.TemporaryDirectory() as td:
            rc, out = rb.default_test_runner(
                [sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(4)"], td
            )
            self.assertEqual(rc, 4)
            self.assertIn("boom", out)


# ---------------------------------------------------------------------------------------------
# T4 — `plan`: the priced matrix, and `run`'s structural refusal (PLAN D1/D6/D10).


#: Fixture pricing dict: fake ids across all four `ce.TIER_ORDER` tiers plus `task_profiles`.
#: Numbers are hand-computable and NEVER match `data/pricing.json` -- the whole point is that
#: `estimate_dispatch_usd`'s arithmetic can be checked independently of any real price.
FIXTURE_PRICING = {
    "cached_date": "2020-01-01",
    # Deliberately NOT the real multipliers (data/pricing.json owns those) -- round fake
    # numbers so `price_usage`'s cache arithmetic can be hand-checked here.
    "cache_read_multiplier": 0.5,
    "cache_write_multiplier_5m": 2.0,
    "models": {
        "fake-haiku-1": {"tier": "haiku", "input_per_mtok": 1.0, "output_per_mtok": 5.0},
        "fake-sonnet-1": {"tier": "sonnet", "input_per_mtok": 3.0, "output_per_mtok": 15.0},
        "fake-opus-1": {"tier": "opus", "input_per_mtok": 5.0, "output_per_mtok": 25.0},
        "fake-frontier-1": {"tier": "frontier", "input_per_mtok": 10.0, "output_per_mtok": 50.0},
    },
    "task_profiles": {
        "XS": {"input_tokens": 1000, "output_tokens": 100},
        "S": {"input_tokens": 4000, "output_tokens": 400},
        "M": {"input_tokens": 10000, "output_tokens": 1000},
        "L": {"input_tokens": 20000, "output_tokens": 2000},
    },
}


class EstimateDispatchUsdTests(unittest.TestCase):
    """Hand-computed against FIXTURE_PRICING (never a real price) -- D10's "the only local
    arithmetic is tokens/1e6 x rate"."""

    def test_hand_computed_xs_haiku(self):
        cost = rb.estimate_dispatch_usd("fake-haiku-1", "XS", FIXTURE_PRICING)
        self.assertAlmostEqual(cost, (1000 * 1.0 + 100 * 5.0) / 1e6)
        self.assertAlmostEqual(cost, 0.0015)

    def test_hand_computed_m_opus(self):
        cost = rb.estimate_dispatch_usd("fake-opus-1", "M", FIXTURE_PRICING)
        self.assertAlmostEqual(cost, (10000 * 5.0 + 1000 * 25.0) / 1e6)
        self.assertAlmostEqual(cost, 0.075)

    def test_hand_computed_s_sonnet(self):
        cost = rb.estimate_dispatch_usd("fake-sonnet-1", "S", FIXTURE_PRICING)
        self.assertAlmostEqual(cost, (4000 * 3.0 + 400 * 15.0) / 1e6)
        self.assertAlmostEqual(cost, 0.018)

    def test_unknown_model_raises_key_error(self):
        with self.assertRaises(KeyError):
            rb.estimate_dispatch_usd("not-a-real-model", "XS", FIXTURE_PRICING)

    def test_unknown_profile_raises_key_error(self):
        with self.assertRaises(KeyError):
            rb.estimate_dispatch_usd("fake-haiku-1", "NOT-A-PROFILE", FIXTURE_PRICING)


class DefaultJudgeTests(unittest.TestCase):
    """PLAN D6: default judge = highest populated tier not fully consumed by candidates,
    first model in pricing-file order within that tier."""

    def test_default_judge_is_the_highest_tier_not_a_candidate(self):
        judge = rb._default_judge_id(FIXTURE_PRICING, ["fake-haiku-1", "fake-sonnet-1"])
        self.assertEqual(judge, "fake-frontier-1")

    def test_default_judge_skips_a_tier_fully_consumed_by_candidates(self):
        judge = rb._default_judge_id(FIXTURE_PRICING, ["fake-haiku-1", "fake-frontier-1"])
        self.assertEqual(judge, "fake-opus-1")

    def test_default_judge_is_none_when_every_model_is_a_candidate(self):
        judge = rb._default_judge_id(
            FIXTURE_PRICING,
            ["fake-haiku-1", "fake-sonnet-1", "fake-opus-1", "fake-frontier-1"],
        )
        self.assertIsNone(judge)

    def test_build_plan_default_judge_excludes_the_candidates(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_fixture_repo(repo)
            card = rb.build_plan(
                repo, ["fake-haiku-1", "fake-sonnet-1"], pricing=FIXTURE_PRICING,
                scratch_dir=td / "scratch",
            )
            self.assertEqual(card["judge"], "fake-frontier-1")
            self.assertNotIn(card["judge"], card["candidates"])

    def test_explicit_judge_equal_to_a_candidate_is_a_hard_refusal(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_fixture_repo(repo)
            with self.assertRaises(ValueError) as ctx:
                rb.build_plan(
                    repo, ["fake-haiku-1", "fake-sonnet-1"], judge="fake-haiku-1",
                    pricing=FIXTURE_PRICING, scratch_dir=td / "scratch",
                )
            self.assertIn("fake-haiku-1", str(ctx.exception))

    def test_no_eligible_judge_raises_value_error(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_fixture_repo(repo)
            with self.assertRaises(ValueError):
                rb.build_plan(
                    repo,
                    ["fake-haiku-1", "fake-sonnet-1", "fake-opus-1", "fake-frontier-1"],
                    pricing=FIXTURE_PRICING, scratch_dir=td / "scratch",
                )


class BuildPlanMatrixTests(unittest.TestCase):
    """Matrix + totals wiring: every cell traces back to `estimate_dispatch_usd` against the
    FIXTURE dict, and totals are exact sums of the cells that feed them."""

    def test_matrix_and_totals_trace_to_the_fixture_dict(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            card = rb.build_plan(
                repo, ["fake-haiku-1", "fake-sonnet-1"], pricing=FIXTURE_PRICING,
                scratch_dir=td / "scratch",
            )
            self.assertEqual(card["mode"], "issue-replay")
            self.assertEqual(len(card["tasks"]), 2)
            self.assertEqual(len(card["matrix"]), 2 * 2)  # 2 tasks x 2 candidates
            self.assertEqual(len(card["judge_grades"]), 2 * 2)

            by_task = {t["task_id"]: t for t in card["tasks"]}
            for row in card["matrix"]:
                task = by_task[row["task_id"]]
                expected = rb.estimate_dispatch_usd(
                    row["candidate"], task["size_profile"], FIXTURE_PRICING
                )
                self.assertAlmostEqual(row["estimated_usd"], expected)

            judge_unit = rb.estimate_dispatch_usd(
                card["judge"], rb.JUDGE_GRADE_PROFILE, FIXTURE_PRICING
            )
            for row in card["judge_grades"]:
                self.assertAlmostEqual(row["estimated_usd"], judge_unit)

            for cid in card["candidates"]:
                expected_total = sum(
                    r["estimated_usd"] for r in card["matrix"] if r["candidate"] == cid
                )
                self.assertAlmostEqual(card["totals"]["by_candidate"][cid], expected_total)

            expected_judge_total = sum(r["estimated_usd"] for r in card["judge_grades"])
            self.assertAlmostEqual(card["totals"]["judge_total"], expected_judge_total)
            expected_grand = (
                sum(card["totals"]["by_candidate"].values()) + card["totals"]["judge_total"]
            )
            self.assertAlmostEqual(card["totals"]["grand_total"], expected_grand)

    def test_estimate_caveat_label_present(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_fixture_repo(repo)
            card = rb.build_plan(
                repo, ["fake-haiku-1"], pricing=FIXTURE_PRICING, scratch_dir=td / "scratch",
            )
            self.assertIn(rb.ESTIMATE_CAVEAT_LABEL, card["labels"])
            self.assertIn("not a bill", rb.ESTIMATE_CAVEAT_LABEL)

    def test_unknown_candidate_propagates_resolve_model_key_error(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_fixture_repo(repo)
            with self.assertRaises(KeyError) as ctx:
                rb.build_plan(
                    repo, ["totally-not-a-model-or-tier"], pricing=FIXTURE_PRICING,
                    scratch_dir=td / "scratch",
                )
            self.assertIn("totally-not-a-model-or-tier", str(ctx.exception))

    def test_candidates_are_deduped_order_preserving(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_fixture_repo(repo)
            card = rb.build_plan(
                repo, ["fake-sonnet-1", "fake-haiku-1", "fake-sonnet-1"],
                pricing=FIXTURE_PRICING, scratch_dir=td / "scratch",
            )
            self.assertEqual(card["candidates"], ["fake-sonnet-1", "fake-haiku-1"])


class ModeReasonOracleCountTests(unittest.TestCase):
    """F9 (Phase 1 review) — `choose_mode` counts PAIRS, not objectively-scorable ones, so an
    auto (or forced) issue-replay pick can be below the D7 floor without saying so anywhere
    else. The mode reason must print the oracle-available count alongside the pair count."""

    def test_reason_prints_oracle_available_count_alongside_pair_count(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)  # 2 pairs mined: #7 (oracled), #9 (not)
            card = rb.build_plan(
                repo, ["fake-haiku-1"], pricing=FIXTURE_PRICING, scratch_dir=td / "scratch",
            )
            self.assertEqual(card["mode"], "issue-replay")
            self.assertIn("1/2", card["mode_reason"])
            self.assertIn("objectively scorable", card["mode_reason"])
            self.assertIn(str(rb.MIN_EVIDENCE_TASKS), card["mode_reason"])

    def test_forced_issue_replay_mode_still_carries_the_oracle_count(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            card = rb.build_plan(
                repo, ["fake-haiku-1"], mode="issue-replay", pricing=FIXTURE_PRICING,
                scratch_dir=td / "scratch",
            )
            self.assertIn("1/2", card["mode_reason"])

    def test_general_mode_reason_carries_no_oracle_count_annotation(self):
        # general-mode tasks are ALWAYS oracle_tests_available=True by schema -- the
        # annotation is specifically an issue-replay below-floor signal (F9), not a universal
        # suffix, so it must not appear when general mode is the resolved mode.
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            head, _ = build_parity_fixture_repo(repo)
            card = rb.build_plan(
                repo, ["fake-haiku-1"], mode="general", test_cmd="run-tests",
                test_runner=_ge_marker_runner, pricing=FIXTURE_PRICING,
                scratch_dir=td / "scratch",
            )
            self.assertEqual(card["mode"], "general")
            self.assertNotIn("objectively scorable", card["mode_reason"])

    def test_auto_mode_without_test_cmd_falls_back_to_issue_replay_regardless_of_floor(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)  # only 2 pairs -- below MIN_EVIDENCE_TASKS
            card = rb.build_plan(
                repo, ["fake-haiku-1"], mode="auto", test_cmd=None, pricing=FIXTURE_PRICING,
                scratch_dir=td / "scratch",
            )
            self.assertEqual(card["mode"], "issue-replay")
            self.assertIn("no --test-cmd", card["mode_reason"])
            self.assertIn("1/2", card["mode_reason"])


class PartialCoveragePlanLabelTests(unittest.TestCase):
    """F8 (Phase 1 review) — `mine_general_tasks` truncating its bounded scan (`limit * 4`
    sites) below `limit` admitted tasks must surface as an explicit label on the plan card,
    not just a note buried in the mining pass."""

    def test_partial_coverage_label_appears_when_the_scan_bound_truncates(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            root = repo
            root.mkdir(parents=True, exist_ok=True)
            _git(root, "init", "-q")
            # 10 independent >= sites, all green under this always-green stub -- nothing gets
            # admitted, so the scan must stop on the examined-count bound (limit * 4).
            body = "".join(f"def f{i}(x):\n    return x >= {i}\n\n" for i in range(10))
            (root / "many.py").write_text(body)
            _git(root, "add", "-A")
            _git(root, "commit", "-q", "-m", "many sites")

            def always_green(cmd, cwd):
                return 0, "always green"

            card = rb.build_plan(
                repo, ["fake-haiku-1"], mode="general", limit=2, test_cmd="run-tests",
                test_runner=always_green, pricing=FIXTURE_PRICING, scratch_dir=td / "scratch",
            )
            self.assertEqual(card["tasks"], [])
            partial = [l for l in card["labels"] if "partial coverage" in l]
            self.assertTrue(partial, card["labels"])
            self.assertIn("limit * 4", partial[0])
            self.assertIn("partial coverage", " | ".join(card["notes"]))

    def test_no_partial_coverage_label_when_the_repo_is_scanned_exhaustively(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            head, _ = build_parity_fixture_repo(repo)
            card = rb.build_plan(
                repo, ["fake-haiku-1"], mode="general", test_cmd="run-tests",
                test_runner=_ge_marker_runner, pricing=FIXTURE_PRICING,
                scratch_dir=td / "scratch",
            )
            self.assertTrue(card["tasks"])
            self.assertFalse([l for l in card["labels"] if "partial coverage" in l])


class PlanCliTests(unittest.TestCase):
    """CLI-level: real `data/pricing.json`, real tier words -- exactly what a user types."""

    def test_json_output_shape(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_fixture_repo(repo)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rb.main(["plan", "--repo", str(repo), "--models", "haiku,sonnet", "--json"])
            card = json.loads(out.getvalue())
            self.assertTrue(card["judge"])
            self.assertNotIn(card["judge"], card["candidates"])
            self.assertTrue(any("not a bill" in l for l in card["labels"]))

    def test_markdown_output_has_the_go_live_hint(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_fixture_repo(repo)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rb.main(["plan", "--repo", str(repo), "--models", "haiku"])
            text = out.getvalue()
            self.assertIn("to spend: rerun with run --live --max-usd <ceiling>", text)
            self.assertIn("## matrix", text)

    def test_plan_never_writes_the_real_store(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_fixture_repo(repo)
            store = rb.DEFAULT_STORE_DIR
            before = sorted(p.name for p in store.iterdir()) if store.is_dir() else None
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rb.main(["plan", "--repo", str(repo), "--models", "haiku", "--json"])
            after = sorted(p.name for p in store.iterdir()) if store.is_dir() else None
            self.assertEqual(before, after, "plan wrote into the real benchruns store")


class RunCliTests(unittest.TestCase):
    """CLI-level `run` gating (PLAN D1) -- real pricing, real tier words."""

    def test_missing_live_and_max_usd_refuses_and_leaves_no_run_dir(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_fixture_repo(repo)
            store = td / "store"
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                    self.assertRaises(SystemExit) as ctx:
                rb.main([
                    "run", "--repo", str(repo), "--models", "haiku", "--store-dir", str(store),
                ])
            self.assertEqual(ctx.exception.code, 2)
            self.assertIn("--live", err.getvalue())
            self.assertIn("--max-usd", err.getvalue())
            self.assertIn("refusing to dispatch", err.getvalue())
            self.assertIn("repo-bench plan", out.getvalue())
            self.assertFalse(
                store.exists() and any(store.iterdir()),
                "a run dir was left in the store after a missing-flags refusal",
            )

    def test_ceiling_exceeded_refuses_and_leaves_no_run_dir(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_fixture_repo(repo)
            store = td / "store"
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                    self.assertRaises(SystemExit) as ctx:
                rb.main([
                    "run", "--repo", str(repo), "--models", "haiku", "--store-dir", str(store),
                    "--live", "--max-usd", "0.0000001",
                ])
            self.assertEqual(ctx.exception.code, 2)
            self.assertIn("exceeds --max-usd", err.getvalue())
            self.assertIn("repo-bench plan", out.getvalue())
            self.assertFalse(
                store.exists() and any(store.iterdir()),
                "a run dir was left in the store after a ceiling-exceeded refusal",
            )

    def test_live_without_max_usd_still_refuses(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_fixture_repo(repo)
            store = td / "store"
            # stdout redirected too (T5R/F9's housekeeping half): the refusal path prints the
            # whole plan card, and an unredirected one lands in the suite's own output.
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                    self.assertRaises(SystemExit) as ctx:
                rb.main([
                    "run", "--repo", str(repo), "--models", "haiku", "--store-dir", str(store),
                    "--live",
                ])
            self.assertEqual(ctx.exception.code, 2)
            self.assertIn("--max-usd", err.getvalue())

    def test_sufficient_ceiling_records_plan_json_under_a_new_run_dir(self):
        # NARROWED BY T5 (the same shape T4 narrowed T1's "unimplemented subcommands" test):
        # this used to drive `rb.main`, whose dispatch tail was a no-op stub. T5 makes that
        # tail dispatch for real, so driving it through `main` with no injected runner would
        # invoke the actual `claude` binary and spend the user's money. The gating assertions
        # it was written for are unchanged; the dispatch now rides an injected stub.
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_fixture_repo(repo)
            store = td / "store"
            runner = make_stub_runner()
            out = io.StringIO()
            args = rb.build_parser().parse_args([
                "run", "--repo", str(repo), "--models", "haiku", "--store-dir", str(store),
                "--live", "--max-usd", "1000000",
            ])
            with contextlib.redirect_stdout(out):
                rb.cmd_run(args, runner=runner)
            self.assertIn("completed:", out.getvalue())
            rows, notes = rb.list_runs(store)
            self.assertEqual(len(rows), 1, notes)
            run_dir = Path(rows[0]["path"])
            plan_path = run_dir / "plan.json"
            self.assertTrue(plan_path.exists())
            card = json.loads(plan_path.read_text())
            self.assertTrue(card["candidates"])
            self.assertNotIn(card["judge"], card["candidates"])
            self.assertIn(rb.ESTIMATE_CAVEAT_LABEL, card["labels"])

    def test_non_finite_or_negative_ceiling_refuses_and_leaves_no_run_dir(self):
        # `--max-usd nan` parses cleanly through argparse's `type=float` yet defeats every
        # `x > ceiling` comparison (IEEE-754: nan compares False against everything) -- the
        # same disqualifying defeat applies to inf (nothing is ever "over" it) and to a
        # negative ceiling (nonsensical as a spend cap). Each must refuse with exit 2 and
        # leave the store exactly as untouched as the other refusal paths above. Passed as
        # `--max-usd=<value>` (one token) rather than two separate argv tokens: argparse's
        # own negative-number heuristic mis-tokenizes a bare `-inf`/`-1` as a second option
        # when passed as `["--max-usd", "-inf"]`, which would exit 2 for an unrelated
        # reason (missing this fix's own refusal path entirely) rather than exercising
        # `validate_ceiling`.
        for bad in ("nan", "inf", "-inf", "-1"):
            with tempfile.TemporaryDirectory() as td:
                td = Path(td)
                repo = td / "target"
                build_fixture_repo(repo)
                store = td / "store"
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                        self.assertRaises(SystemExit) as ctx:
                    rb.main([
                        "run", "--repo", str(repo), "--models", "haiku",
                        "--store-dir", str(store), "--live", f"--max-usd={bad}",
                    ])
                self.assertEqual(ctx.exception.code, 2, f"--max-usd {bad}: {err.getvalue()}")
                self.assertIn("--max-usd", err.getvalue())
                self.assertIn(bad, err.getvalue())
                self.assertFalse(
                    store.exists() and any(store.iterdir()),
                    f"--max-usd {bad} left a run dir in the store: {err.getvalue()}",
                )


class ValidateCeilingTests(unittest.TestCase):
    """`validate_ceiling` is the ONE named, importable guard both `cmd_run`'s structural
    check and T5's per-dispatch re-check must share -- covered independently of the CLI."""

    def test_accepts_a_normal_finite_ceiling_unchanged(self):
        self.assertEqual(rb.validate_ceiling(5.0), 5.0)
        self.assertEqual(rb.validate_ceiling(0.0), 0.0)

    def test_accepts_none_as_not_yet_set(self):
        self.assertIsNone(rb.validate_ceiling(None))

    def test_rejects_nan(self):
        with self.assertRaises(ValueError) as ctx:
            rb.validate_ceiling(float("nan"))
        self.assertIn("nan", str(ctx.exception).lower())

    def test_rejects_positive_infinity(self):
        with self.assertRaises(ValueError):
            rb.validate_ceiling(float("inf"))

    def test_rejects_negative_infinity(self):
        with self.assertRaises(ValueError):
            rb.validate_ceiling(float("-inf"))

    def test_rejects_negative_finite_value(self):
        with self.assertRaises(ValueError):
            rb.validate_ceiling(-1.0)


class ScratchDirUnderRunDirTests(unittest.TestCase):
    """F11b (Phase 1 review) — `mine_general_tasks`'s scratch sandboxes must live under
    `<run-dir>/work`, never a system temp dir, whenever `cmd_run` is the caller: a run dir
    exists there to put them under (PLAN D3/D11)."""

    def test_cmd_run_success_path_mines_general_scratch_under_the_run_dir(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_parity_fixture_repo(repo)
            store = td / "store"
            py = shlex.quote(sys.executable)
            # A REAL (but harmless, local, stdlib-only) test command: red exactly when the
            # `>=` site has been flipped to `>` -- the shell-string path `default_test_runner`
            # actually runs, exercised end-to-end through `run` for the first time here.
            test_cmd = (
                f"{py} -c \"import sys; c = open('calc.py').read(); "
                f"sys.exit(1 if 'x > 10' in c else 0)\""
            )
            # Narrowed by T5 for the same reason as RunCliTests above: the dispatch tail is
            # real now, so the runner is injected. Re-narrowed by T5R/F1: a mining scratch
            # sandbox is now swept as soon as its red check is done, so the proof that it was
            # built under `<run-dir>/work` is the argument it was handed, not a leftover
            # directory — and its ABSENCE afterwards is itself the new property.
            captured = {}
            orig = rb.mine_general_tasks

            def spy(*a, **kw):
                captured["scratch_dir"] = kw.get("scratch_dir")
                return orig(*a, **kw)

            out = io.StringIO()
            args = rb.build_parser().parse_args([
                "run", "--repo", str(repo), "--models", "haiku", "--mode", "general",
                "--test-cmd", test_cmd, "--store-dir", str(store),
                "--live", "--max-usd", "1000000",
            ])
            with mock.patch.object(rb, "mine_general_tasks", spy):
                with contextlib.redirect_stdout(out):
                    rb.cmd_run(args, runner=make_stub_runner())
            self.assertIn("completed:", out.getvalue())
            rows, notes = rb.list_runs(store)
            self.assertEqual(len(rows), 1, notes)
            run_dir = Path(rows[0]["path"])
            work_dir = run_dir / "work"
            self.assertEqual(Path(captured["scratch_dir"]), work_dir)
            leftovers = sorted(p.name for p in work_dir.iterdir()) if work_dir.exists() else []
            self.assertFalse(
                [name for name in leftovers if name.startswith("site-")],
                f"a mining scratch sandbox survived under {work_dir}: {leftovers}",
            )
            card = json.loads((run_dir / "plan.json").read_text())
            self.assertEqual(card["mode"], "general")
            self.assertTrue(card["tasks"])

    def test_refused_run_still_mines_under_the_run_dir_before_cleanup(self):
        # Even on a refusal, mining happens (the plan must be printed) -- prove it used
        # `<run-dir>/work`, not a system temp dir, by spying on mine_general_tasks's
        # scratch_dir argument before the run dir is removed.
        #
        # T5R/F9: this used to drive `main()`, which takes no runner arguments, so the bare
        # `--test-cmd run-tests` went to `default_test_runner` and `subprocess.run(...,
        # shell=True)` really did PATH-resolve a command called `run-tests` during
        # `unittest discover`. It calls `cmd_run` directly now, with BOTH runners injected,
        # and its plan card no longer lands in the suite's stdout.
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_parity_fixture_repo(repo)
            store = td / "store"

            captured = {}
            orig = rb.mine_general_tasks

            def spy(*args, **kwargs):
                captured["scratch_dir"] = kwargs.get("scratch_dir")
                return orig(*args, **kwargs)

            err = io.StringIO()
            out = io.StringIO()
            args = rb.build_parser().parse_args([
                "run", "--repo", str(repo), "--models", "haiku", "--mode", "general",
                "--test-cmd", "run-tests", "--store-dir", str(store),
                # no --live / --max-usd -> refusal path
            ])
            with mock.patch.object(rb, "mine_general_tasks", spy):
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                        self.assertRaises(SystemExit):
                    rb.cmd_run(
                        args, runner=_explode_runner, test_runner=_ge_marker_runner,
                    )
            self.assertIn("refusing to dispatch", err.getvalue())
            self.assertIsNotNone(captured.get("scratch_dir"))
            self.assertEqual(Path(captured["scratch_dir"]).name, "work")
            self.assertEqual(Path(captured["scratch_dir"]).parent.parent, store)
            self.assertFalse(
                store.exists() and any(store.iterdir()),
                "a run dir was left in the store after a missing-flags refusal",
            )


# ---------------------------------------------------------------------------------------------
# T5 — the harness seam and the live dispatch loop (PLAN D1/D2).
#
# THE POINT OF THIS BLOCK: prove that the one code path in this repo that could spend real
# money cannot do so from a test. Every dispatch below goes through an INJECTED runner; no
# `claude` binary exists anywhere in this file, `default_dispatch_runner` is booby-trapped in
# the full-run test, and the target repo is checked byte-for-byte afterwards.


#: Canned token counts a stub returns. Obviously synthetic -- priced through the same
#: `data/pricing.json` path a real run uses, never against a hardcoded dollar figure.
STUB_USAGE = {"input_tokens": 1000, "output_tokens": 200}


def _canned_result_json(usage=STUB_USAGE):
    """A harness result envelope in the shape `extract_usage` reads (`type`/`usage`)."""
    payload = {"type": "result", "subtype": "success"}
    if usage is not None:
        payload["usage"] = usage
    return json.dumps(payload)


def make_stub_runner(usage=STUB_USAGE, output=None, rc=0, filename="candidate_fix.py",
                     content="# the candidate's change\n"):
    """An INJECTED dispatch runner: records every (argv, cwd), writes a change into the
    sandbox it is handed, and returns canned harness output. No binary, no network, no money.

    `output=` overrides the canned envelope (used to prove that garbage degrades to
    `usd_basis: estimated` instead of inventing a number); `filename=None` simulates a
    candidate that changed nothing.
    """
    calls = []

    def runner(argv, cwd):
        calls.append({"argv": list(argv), "cwd": str(cwd)})
        if filename:
            (Path(cwd) / filename).write_text(content)
        return rc, _canned_result_json(usage) if output is None else output

    runner.calls = calls
    return runner


def _explode_runner(argv, cwd):
    raise AssertionError(
        "default_dispatch_runner was reached from a test — that is the path to the REAL "
        "`claude` binary and real money"
    )


def _run_args(repo, store, *extra):
    return rb.build_parser().parse_args([
        "run", "--repo", str(repo), "--models", "haiku", "--store-dir", str(store), *extra,
    ])


def _grand_total(repo, models, scratch, **kw):
    """The real-pricing plan total for a fixture repo -- so a test ceiling can be set relative
    to it instead of to a magic number that pricing drift could invalidate."""
    card = rb.build_plan(repo, models, scratch_dir=scratch, **kw)
    return card["totals"]["grand_total"]


class OutputFormatConstantTests(unittest.TestCase):
    def test_constant_is_the_pinned_pair(self):
        self.assertEqual(rb.OUTPUT_FORMAT_ARGS, ("--output-format", "json"))

    def test_argv_carries_output_format_requires_adjacency(self):
        self.assertTrue(rb.argv_carries_output_format(["x", "--output-format", "json", "p"]))
        self.assertFalse(
            rb.argv_carries_output_format(["--output-format", "--model", "json"]),
            "a flag separated from its value is not the same command line",
        )
        self.assertFalse(rb.argv_carries_output_format([]))

    def test_the_permission_flag_is_never_re_derived_here(self):
        # PLAN D2: the argv shape belongs to claude_execute. The only sanctioned mention of
        # its permission flag in this module is a qualified reference to that module's own.
        src = (BIN_DIR / "repo_bench.py").read_text()
        stripped = src.replace("ce.PERMISSION_FLAG", "").replace(
            "claude_execute.PERMISSION_FLAG", ""
        )
        self.assertNotIn("PERMISSION_FLAG", stripped)
        self.assertNotIn("--dangerously-skip-permissions", src)


class ClaudeAdapterTests(unittest.TestCase):
    """PLAN D2 — the adapter is a plain seam, and its argv is claude_execute's, not ours."""

    def test_adapter_shape(self):
        self.assertEqual(rb.CLAUDE_ADAPTER["name"], "claude")
        self.assertTrue(callable(rb.CLAUDE_ADAPTER["build_argv"]))
        self.assertTrue(callable(rb.CLAUDE_ADAPTER["extract_usage"]))

    def test_build_argv_is_claude_execute_build_dispatch_verbatim(self):
        ce = _load("claude_execute")
        expected = ce.build_dispatch(
            "stub-bin", "fake-haiku-1", "do the thing", extra_args=rb.OUTPUT_FORMAT_ARGS
        )
        actual = rb.CLAUDE_ADAPTER["build_argv"]("stub-bin", "fake-haiku-1", "do the thing")
        self.assertEqual(actual, expected)

    def test_build_argv_carries_the_output_format_and_ends_with_the_prompt(self):
        argv = rb.build_claude_argv("stub-bin", "fake-haiku-1", "PROMPT")
        self.assertTrue(rb.argv_carries_output_format(argv))
        self.assertEqual(argv[0], "stub-bin")
        self.assertEqual(argv[-1], "PROMPT")


class ExtractUsageTests(unittest.TestCase):
    """PLAN D2/R1 — best-effort parsing; ANY miss is None, never a guessed token count."""

    def test_no_json_at_all(self):
        self.assertIsNone(rb.extract_usage("no json here at all"))

    def test_empty_output(self):
        self.assertIsNone(rb.extract_usage(""))
        self.assertIsNone(rb.extract_usage(None))

    def test_json_without_usage(self):
        self.assertIsNone(rb.extract_usage('{"type": "result", "subtype": "success"}'))

    def test_valid_result_envelope(self):
        usage = rb.extract_usage(_canned_result_json())
        self.assertEqual(usage, STUB_USAGE)

    def test_envelope_surrounded_by_noise(self):
        noisy = f"warning: something\n{_canned_result_json()}\ntrailing chatter\n"
        self.assertEqual(rb.extract_usage(noisy), STUB_USAGE)

    def test_last_object_with_usage_wins(self):
        first = json.dumps({"usage": {"input_tokens": 1, "output_tokens": 1}})
        last = json.dumps({"usage": {"input_tokens": 9, "output_tokens": 9}})
        self.assertEqual(
            rb.extract_usage(f"{first}\n{last}"), {"input_tokens": 9, "output_tokens": 9}
        )

    def test_cache_keys_are_carried_when_present(self):
        usage = rb.extract_usage(json.dumps({"usage": {
            "input_tokens": 10, "output_tokens": 20,
            "cache_read_input_tokens": 30, "cache_creation_input_tokens": 40,
        }}))
        self.assertEqual(usage["cache_read_input_tokens"], 30)
        self.assertEqual(usage["cache_creation_input_tokens"], 40)

    def test_absent_cache_keys_are_absent_not_zero(self):
        usage = rb.extract_usage(_canned_result_json())
        self.assertNotIn("cache_read_input_tokens", usage)

    def test_non_numeric_count_is_a_refusal(self):
        self.assertIsNone(rb.extract_usage(json.dumps({"usage": {
            "input_tokens": "lots", "output_tokens": 5,
        }})))

    def test_missing_output_tokens_is_a_refusal(self):
        self.assertIsNone(rb.extract_usage(json.dumps({"usage": {"input_tokens": 5}})))

    def test_truncated_json_is_a_refusal(self):
        self.assertIsNone(rb.extract_usage('{"usage": {"input_tokens": 5, "output'))


class PriceUsageTests(unittest.TestCase):
    """Hand-computed against FIXTURE_PRICING -- never a real price (PLAN D10)."""

    def test_input_and_output_tokens(self):
        usd = rb.price_usage("fake-haiku-1", {"input_tokens": 1000, "output_tokens": 200},
                             FIXTURE_PRICING)
        self.assertAlmostEqual(usd, (1000 * 1.0 + 200 * 5.0) / 1e6)

    def test_cache_tokens_use_the_pricing_multipliers(self):
        usd = rb.price_usage("fake-sonnet-1", {
            "input_tokens": 1000, "output_tokens": 100,
            "cache_read_input_tokens": 2000, "cache_creation_input_tokens": 500,
        }, FIXTURE_PRICING)
        expected = (
            1000 * 3.0 + 100 * 15.0 + 2000 * 3.0 * 0.5 + 500 * 3.0 * 2.0
        ) / 1e6
        self.assertAlmostEqual(usd, expected)

    def test_missing_multiplier_with_cache_tokens_degrades_to_none(self):
        pricing = dict(FIXTURE_PRICING)
        pricing.pop("cache_read_multiplier")
        usd = rb.price_usage("fake-haiku-1", {
            "input_tokens": 10, "output_tokens": 10, "cache_read_input_tokens": 1000,
        }, pricing)
        self.assertIsNone(usd, "cache tokens were silently dropped instead of degrading")

    def test_empty_usage_is_none(self):
        self.assertIsNone(rb.price_usage("fake-haiku-1", None, FIXTURE_PRICING))
        self.assertIsNone(rb.price_usage("fake-haiku-1", {}, FIXTURE_PRICING))

    def test_unknown_model_raises_key_error(self):
        with self.assertRaises(KeyError):
            rb.price_usage("not-a-real-model", STUB_USAGE, FIXTURE_PRICING)

    def test_it_delegates_the_arithmetic_to_cost_report_price(self):
        # F7 (Phase 2 review) — D10 is the kit's sharpest fence: the rates, the cache
        # multipliers and the division belong to `cost_report`. This function may map key
        # NAMES between the harness's vocabulary and `price()`'s, and nothing else.
        cr = rb._cr()
        with mock.patch.object(cr, "price", wraps=cr.price) as spy:
            usd = rb.price_usage("fake-sonnet-1", {
                "input_tokens": 1000, "output_tokens": 100,
                "cache_read_input_tokens": 2000, "cache_creation_input_tokens": 500,
            }, FIXTURE_PRICING)
        self.assertEqual(spy.call_count, 1, "price_usage did not go through cost_report.price")
        key, mapped, _when, pricing = spy.call_args[0]
        self.assertEqual(key, "fake-sonnet-1")
        self.assertEqual(
            mapped, {"input": 1000, "output": 100, "cache_read": 2000, "cache_write": 500}
        )
        self.assertIs(pricing, FIXTURE_PRICING)
        self.assertAlmostEqual(usd, (1000 * 3.0 + 100 * 15.0 + 2000 * 3.0 * 0.5
                                     + 500 * 3.0 * 2.0) / 1e6)

    def test_absent_counts_map_to_zero_not_to_a_missing_key(self):
        # `price()` subscripts all four; a count the harness never reported is genuinely zero
        # tokens of that kind — the one place a 0 is a fact rather than a guess.
        usd = rb.price_usage("fake-haiku-1", {"input_tokens": 10, "output_tokens": 0},
                             FIXTURE_PRICING)
        self.assertAlmostEqual(usd, (10 * 1.0) / 1e6)


class WouldExceedCeilingTests(unittest.TestCase):
    """PLAN D1 + the T4 post-mortem: the per-dispatch check REUSES `validate_ceiling`."""

    def test_under_the_ceiling(self):
        self.assertFalse(rb.would_exceed_ceiling(0.5, 0.4, 1.0))

    def test_over_the_ceiling(self):
        self.assertTrue(rb.would_exceed_ceiling(0.5, 0.6, 1.0))

    def test_exactly_at_the_ceiling_is_allowed(self):
        self.assertFalse(rb.would_exceed_ceiling(0.5, 0.5, 1.0))

    def test_non_finite_ceilings_raise_through_validate_ceiling(self):
        for bad in (float("nan"), float("inf"), float("-inf"), -1.0):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                rb.would_exceed_ceiling(0.0, 0.01, bad)

    def test_missing_ceiling_is_a_refusal_not_a_permissive_default(self):
        with self.assertRaises(ValueError):
            rb.would_exceed_ceiling(0.0, 0.01, None)

    def test_it_calls_the_shared_helper(self):
        with mock.patch.object(rb, "validate_ceiling", wraps=rb.validate_ceiling) as spy:
            rb.would_exceed_ceiling(0.0, 0.01, 1.0)
        self.assertTrue(spy.called, "the per-dispatch check re-derived the ceiling guard")


class DispatchCellTests(unittest.TestCase):
    def _task_and_sandbox(self, td):
        repo = Path(td) / "target"
        shas = build_issue_fixture_repo(repo)
        tasks, _ = rb.mine_issue_tasks(repo, gh_runner=None)
        task = [t for t in tasks if t["issue"] == 7][0]
        info, baseline = rb.prepare_cell_sandbox(task, repo, Path(td) / "cell")
        return repo, shas, task, info, baseline

    def test_record_shape_and_actual_basis(self):
        with tempfile.TemporaryDirectory() as td:
            _repo, _shas, task, info, baseline = self._task_and_sandbox(td)
            runner = make_stub_runner()
            record = rb.dispatch_cell(
                task, "fake-haiku-1", rb.CLAUDE_ADAPTER, info["path"], runner=runner,
                claude_bin="stub-bin", pricing=FIXTURE_PRICING, estimated_usd=0.25,
                baseline_commit=baseline,
            )
            self.assertEqual(set(record), set(rb.DISPATCH_RECORD_KEYS))
            self.assertEqual(record["task_id"], task["task_id"])
            self.assertEqual(record["model"], "fake-haiku-1")
            self.assertEqual(record["usd_basis"], "actual")
            self.assertAlmostEqual(
                record["usd"], rb.price_usage("fake-haiku-1", STUB_USAGE, FIXTURE_PRICING)
            )
            self.assertEqual(record["dispatch_rc"], 0)
            self.assertIsInstance(record["wall_seconds"], float)
            self.assertGreaterEqual(record["wall_seconds"], 0.0)
            self.assertIn("candidate_fix.py", record["patch"])

    def test_runner_receives_the_sandbox_as_cwd_and_the_output_format(self):
        with tempfile.TemporaryDirectory() as td:
            _repo, _shas, task, info, baseline = self._task_and_sandbox(td)
            runner = make_stub_runner()
            rb.dispatch_cell(
                task, "fake-haiku-1", rb.CLAUDE_ADAPTER, info["path"], runner=runner,
                claude_bin="stub-bin", pricing=FIXTURE_PRICING, estimated_usd=0.25,
                baseline_commit=baseline,
            )
            self.assertEqual(len(runner.calls), 1)
            call = runner.calls[0]
            self.assertEqual(Path(call["cwd"]), Path(info["path"]))
            self.assertTrue(rb.argv_carries_output_format(call["argv"]))
            self.assertEqual(call["argv"][0], "stub-bin")

    def test_prompt_never_carries_the_reference_patch(self):
        # The leak fence, re-asserted at the DISPATCH boundary (PLAN R2): what the runner is
        # handed is the only thing the candidate ever sees.
        with tempfile.TemporaryDirectory() as td:
            _repo, _shas, task, info, baseline = self._task_and_sandbox(td)
            runner = make_stub_runner()
            rb.dispatch_cell(
                task, "fake-haiku-1", rb.CLAUDE_ADAPTER, info["path"], runner=runner,
                claude_bin="stub-bin", pricing=FIXTURE_PRICING, estimated_usd=0.25,
                baseline_commit=baseline,
            )
            prompt = runner.calls[0]["argv"][-1]
            for line in task["reference_patch"].splitlines():
                stripped = line[1:].strip()
                if line[:1] in "+-" and not line.startswith(("+++", "---")) and len(stripped) > 10:
                    self.assertNotIn(stripped, prompt)
            for blob in task["test_blobs"].values():
                for line in blob.splitlines():
                    if line.strip():
                        self.assertNotIn(line.strip(), prompt)

    def test_garbage_output_degrades_to_the_plan_estimate(self):
        with tempfile.TemporaryDirectory() as td:
            _repo, _shas, task, info, baseline = self._task_and_sandbox(td)
            runner = make_stub_runner(output="total gibberish, no json, no usage")
            record = rb.dispatch_cell(
                task, "fake-haiku-1", rb.CLAUDE_ADAPTER, info["path"], runner=runner,
                claude_bin="stub-bin", pricing=FIXTURE_PRICING, estimated_usd=0.25,
                baseline_commit=baseline,
            )
            self.assertIsNone(record["usage"])
            self.assertEqual(record["usd_basis"], "estimated")
            self.assertAlmostEqual(record["usd"], 0.25)

    def test_nonzero_rc_is_recorded_not_swallowed(self):
        with tempfile.TemporaryDirectory() as td:
            _repo, _shas, task, info, baseline = self._task_and_sandbox(td)
            runner = make_stub_runner(rc=3, filename=None)
            record = rb.dispatch_cell(
                task, "fake-haiku-1", rb.CLAUDE_ADAPTER, info["path"], runner=runner,
                claude_bin="stub-bin", pricing=FIXTURE_PRICING, estimated_usd=0.25,
                baseline_commit=baseline,
            )
            self.assertEqual(record["dispatch_rc"], 3)
            self.assertEqual(record["patch"], "")


class SetupPatchAppliedAtDispatchTests(unittest.TestCase):
    """F3 (Phase 1 review) — a general-mode candidate sandbox MUST be RED when the model sees
    it. Otherwise the candidate is told "the test suite fails" and handed a passing repo, and
    the entire mode measures nothing while appearing to work."""

    def test_prepare_cell_sandbox_injects_the_bug_and_rebaselines(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            head, _ = build_parity_fixture_repo(repo)
            tasks, _ = rb.mine_general_tasks(
                repo, head, test_cmd="run-tests", test_runner=_ge_marker_runner,
                scratch_dir=td / "scratch",
            )
            task = tasks[0]
            info, baseline = rb.prepare_cell_sandbox(task, repo, td / "cell")
            rc, _ = _ge_marker_runner("run-tests", info["path"])
            self.assertNotEqual(rc, 0, "the candidate's sandbox is GREEN at dispatch time")
            # NARROWED BY T5R2. This used to assert `baseline != info["init_commit"]` -- the
            # baseline had been "moved past" the injected bug by a SECOND commit, which is
            # exactly the leak T5R2 closes. The bug is amended into the root commit now, so
            # the baseline IS the root: the three must agree, and the pre-amend commit no
            # longer exists at all (`git prune`). The property the assertion was written for
            # -- the injected bug is not inside the candidate's diff -- is unchanged below,
            # and is now also checked with no `init_commit=` argument at all.
            self.assertEqual(baseline, info["init_commit"])
            self.assertEqual(baseline, rb.sandbox_init_commit(info["path"]))
            # the injected bug must not show up as the candidate's own work
            self.assertEqual(rb.capture_patch(info["path"], init_commit=baseline), "")
            self.assertEqual(rb.capture_patch(info["path"]), "")
            # T5R/F1: the patch file must survive NOWHERE the candidate can reach -- not in
            # the sandbox (where it would read as the candidate's own work) and not in any
            # ancestor of it either, since reversing a setup patch IS the general-mode answer.
            self.assertFalse(list(td.rglob("*.setup.patch")))

    def test_prepare_cell_sandbox_leaves_one_commit_and_no_mineable_history(self):
        """T5R2 — the sandbox the candidate works in must hold no diff between clean and buggy.

        Before this, `setup_patch` was a SECOND commit: `rev-list --count HEAD` was 2 and
        `git log -p` printed the injected bug as a hunk, so `git diff HEAD~1 HEAD` reversed
        was the answer — readable from the candidate's own cwd, with no ancestor walk and no
        permissions to bypass. Every ancestry fix T5R made was worth nothing next to it.
        """
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            head, _ = build_parity_fixture_repo(repo)
            tasks, _notes = rb.mine_general_tasks(
                repo, head, test_cmd="run-tests", test_runner=_ge_marker_runner,
                scratch_dir=td / "scratch",
            )
            task = tasks[0]
            needles = _solution_needles(task)
            self.assertTrue(needles, "the fixture yielded no solution material to hunt for")

            info, baseline = rb.prepare_cell_sandbox(task, repo, td / "cell")
            sandbox = Path(info["path"])

            # Vacuity guard: these needles are SOLUTION-only. None of them is in the buggy
            # tree the candidate is handed, so a hit anywhere in that sandbox's git surface
            # is a leak and cannot be "the file it was already allowed to read".
            worktree = "".join(p.read_text() for p in sorted(sandbox.rglob("*.py")))
            for needle in needles:
                self.assertNotIn(needle, worktree, "the needle is not solution-only")

            obs = _inspect_sandbox_history(sandbox, needles)
            self.assertEqual(obs["commits"], "1", f"sandbox history is mineable: {obs}")
            self.assertEqual(obs["log_hits"], [], f"the fix is readable in `git log`: {obs}")
            self.assertEqual(
                obs["log_diffs"], [],
                f"a history-free sandbox presented a diff to mine: {obs}",
            )
            self.assertEqual(obs["reflog"], [], f"the reflog survived the amend: {obs}")
            self.assertEqual(
                obs["object_hits"], [],
                f"the pre-amend objects still hold the clean source: {obs}",
            )

            # …and the candidate's own work still captures cleanly against that single root.
            (sandbox / "candidate_fix.py").write_text(CANDIDATE_WORK_MARKER + "\n")
            patch = rb.capture_patch(sandbox)
            self.assertIn("candidate_fix.py", patch)
            self.assertIn(CANDIDATE_WORK_MARKER, patch)
            self.assertEqual(baseline, rb.sandbox_init_commit(sandbox))
            for line in (task["setup_patch"] or "").splitlines():
                if line.startswith("+") and not line.startswith("+++") and len(line) > 8:
                    self.assertNotIn(
                        line[1:].strip(), patch,
                        "capture_patch is reporting the injected bug as candidate work",
                    )

    def test_a_general_mode_run_dispatches_into_a_red_sandbox(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_parity_fixture_repo(repo)
            store = td / "store"

            seen = []

            def red_checking_runner(argv, cwd):
                # T7: the SAME injected runner also carries judge-grading dispatches now, in
                # a bare scratch `cwd` that never held a general-mode sandbox (no `calc.py`)
                # -- only a CANDIDATE dispatch's cwd is a checkout of the fixture repo, so
                # that is the only shape this SETUP-PATCH LAW probe cares about.
                if not (Path(cwd) / "calc.py").exists():
                    return 0, _canned_result_json()
                seen.append(_ge_marker_runner("run-tests", cwd)[0])
                (Path(cwd) / "calc.py").write_text(
                    "def classify(x):\n    if x >= 10:\n        return \"big\"\n"
                    "    return \"small\"\n"
                )
                return 0, _canned_result_json()

            args = rb.build_parser().parse_args([
                "run", "--repo", str(repo), "--models", "haiku", "--mode", "general",
                "--test-cmd", "run-tests", "--store-dir", str(store),
                "--live", "--max-usd", "1000",
            ])
            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_run(args, runner=red_checking_runner, test_runner=_ge_marker_runner)

            self.assertTrue(seen, "no cell was dispatched")
            self.assertTrue(
                all(rc != 0 for rc in seen),
                "a general-mode cell was dispatched into a GREEN sandbox (SETUP-PATCH LAW)",
            )


class RunLoopSafetyTests(unittest.TestCase):
    """The point of T5: a full `run --live --max-usd <enough>` with an INJECTED runner."""

    def _full_run(self, td, models="haiku,sonnet", runner=None, extra=()):
        td = Path(td)
        repo = td / "target"
        build_issue_fixture_repo(repo)
        store = td / "store"
        model_list = models.split(",")
        ceiling = _grand_total(repo, model_list, td / "plan-scratch") * 4 + 1.0
        runner = runner if runner is not None else make_stub_runner()
        args = rb.build_parser().parse_args([
            "run", "--repo", str(repo), "--models", models, "--store-dir", str(store),
            "--live", "--max-usd", str(ceiling), *extra,
        ])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rb.cmd_run(args, runner=runner)
        rows, notes = rb.list_runs(store)
        assert len(rows) == 1, (rows, notes)
        run_dir = Path(rows[0]["path"])
        results = json.loads((run_dir / "results.json").read_text())
        return repo, run_dir, results, runner, out.getvalue()

    def test_every_cell_was_dispatched_through_the_injected_stub(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(rb, "default_dispatch_runner", _explode_runner):
                repo, run_dir, results, runner, text = self._full_run(td)
            # 2 mined issue pairs x 2 candidates
            self.assertEqual(len(results["cells"]), 4)
            # T7: the SAME injected runner also carries one judge grade per cell (PLAN D6) --
            # 4 cell dispatches + 4 judge grades.
            self.assertEqual(len(runner.calls), 8)
            self.assertEqual(len(results["grades"]), 4)
            self.assertEqual(sum(1 for c in results["cells"] if c["skipped"]), 0)
            self.assertEqual(sum(1 for g in results["grades"] if g["skipped"]), 0)
            self.assertIn("completed: 4 cell(s) dispatched", text)
            self.assertEqual(
                len(list((run_dir / "dispatches").glob("*.json"))), 4,
                "one dispatch record per cell must land under dispatches/",
            )

    def test_target_repo_is_byte_identical_after_a_full_run(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            before_head = _git(repo, "rev-parse", "HEAD").strip()
            before_refs = _git(repo, "show-ref")
            before_log = _git(repo, "log", "--format=%H")
            before_tree = _tree_snapshot(repo)

            store = td / "store"
            ceiling = _grand_total(repo, ["haiku"], td / "plan-scratch") * 4 + 1.0
            args = _run_args(repo, store, "--live", "--max-usd", str(ceiling))
            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_run(args, runner=make_stub_runner())

            self.assertEqual(_git(repo, "rev-parse", "HEAD").strip(), before_head)
            self.assertEqual(_git(repo, "status", "--porcelain"), "")
            self.assertEqual(_git(repo, "show-ref"), before_refs)
            self.assertEqual(_git(repo, "log", "--format=%H"), before_log)
            self.assertEqual(_tree_snapshot(repo), before_tree)

    def test_every_argv_carried_the_output_format_args(self):
        with tempfile.TemporaryDirectory() as td:
            _repo, _run_dir, _results, runner, _text = self._full_run(td)
            self.assertTrue(runner.calls)
            for call in runner.calls:
                self.assertTrue(
                    rb.argv_carries_output_format(call["argv"]), call["argv"]
                )
                self.assertEqual(call["argv"][0], rb.DEFAULT_CLAUDE_BIN)

    def test_patches_are_captured_and_dollars_are_actual(self):
        with tempfile.TemporaryDirectory() as td:
            _repo, _run_dir, results, _runner, _text = self._full_run(td)
            for cell in results["cells"]:
                self.assertIn("candidate_fix.py", cell["patch"])
                self.assertEqual(cell["usd_basis"], "actual")
                self.assertIsNotNone(cell["usage"])
            self.assertEqual(results["spend"]["basis"], "actual")
            self.assertGreater(results["spend"]["spent_usd"], 0.0)
            self.assertIn(rb.SPEND_BASIS_LABELS["actual"], results["labels"])

    def test_garbage_harness_output_is_labelled_estimated_everywhere(self):
        with tempfile.TemporaryDirectory() as td:
            runner = make_stub_runner(output="!! not json !!")
            _repo, _run_dir, results, _runner, _text = self._full_run(td, runner=runner)
            for cell in results["cells"]:
                self.assertEqual(cell["usd_basis"], "estimated")
                self.assertAlmostEqual(cell["usd"], cell["estimated_usd"])
            self.assertEqual(results["spend"]["basis"], "estimated")
            self.assertIn(rb.SPEND_BASIS_LABELS["estimated"], results["labels"])

    def test_results_envelope_shape(self):
        with tempfile.TemporaryDirectory() as td:
            _repo, run_dir, results, _runner, text = self._full_run(td, models="haiku")
            self.assertEqual(results["store_schema_version"], rb.STORE_SCHEMA_VERSION)
            self.assertEqual(results["run_id"], run_dir.name)
            self.assertIsInstance(results["repo"], str)
            self.assertTrue(results["base_commit"])
            self.assertEqual(results["mode"], "issue-replay")
            self.assertEqual(results["harness"], "claude")
            self.assertTrue(results["candidates"])
            self.assertNotIn(results["judge"], results["candidates"])
            self.assertEqual(set(results["spend"]), {"ceiling_usd", "spent_usd", "basis"})
            self.assertIn(results["spend"]["basis"], ("actual", "estimated", "mixed"))
            # T7: judge grading is wired into the loop now -- one grade per cell, each its own
            # priced dispatch (PLAN D6), through the SAME runner every candidate cell uses.
            self.assertEqual(len(results["grades"]), len(results["cells"]))
            for grade in results["grades"]:
                self.assertEqual(grade["oracle"], "judge")
                self.assertEqual(grade["judge_model"], results["judge"])
                self.assertEqual(grade["label"], rb.JUDGE_LABEL)
                self.assertIn(set(grade["slots"]), ({"A", "B"},))
            self.assertNotIn(rb.COST_CEILING_LABEL, results["labels"])
            self.assertIn(str(run_dir / "results.json"), text)

    def test_mined_task_records_land_in_the_store_never_in_the_sandbox(self):
        with tempfile.TemporaryDirectory() as td:
            _repo, run_dir, results, _runner, _text = self._full_run(
                td, models="haiku", extra=("--keep-work",)
            )
            stored = list((run_dir / "tasks").glob("*.json"))
            self.assertEqual(len(stored), len(results["cells"]))
            blobs = [
                json.loads(p.read_text()) for p in stored
            ]
            self.assertTrue(any(b["reference_patch"] for b in blobs))
            # …and none of that reached a candidate's sandbox
            for cell_dir in (run_dir / "work").iterdir():
                if not cell_dir.is_dir():
                    continue
                for blob in blobs:
                    for path in blob["test_blobs"]:
                        self.assertFalse(
                            (cell_dir / path).exists(),
                            f"fix-test blob {path} leaked into the candidate sandbox",
                        )

    def test_cell_sandboxes_live_under_the_run_dir_and_are_swept(self):
        # F11b — PLAN D3/D11's "all mutation happens under the run dir" must be literally true.
        with tempfile.TemporaryDirectory() as td:
            _repo, run_dir, _results, _runner, _text = self._full_run(
                td, models="haiku", extra=("--keep-work",)
            )
            kept = sorted(p.name for p in (run_dir / "work").iterdir() if p.is_dir())
            self.assertTrue([n for n in kept if n.startswith("cell-")], kept)

        with tempfile.TemporaryDirectory() as td:
            _repo, run_dir, _results, _runner, _text = self._full_run(td, models="haiku")
            swept = sorted(p.name for p in (run_dir / "work").iterdir() if p.is_dir())
            self.assertFalse(
                [n for n in swept if n.startswith("cell-")],
                f"cell sandboxes survived without --keep-work: {swept}",
            )

    def test_the_run_never_writes_the_real_store(self):
        store = rb.DEFAULT_STORE_DIR
        before = sorted(p.name for p in store.iterdir()) if store.is_dir() else None
        with tempfile.TemporaryDirectory() as td:
            self._full_run(td, models="haiku")
        after = sorted(p.name for p in store.iterdir()) if store.is_dir() else None
        self.assertEqual(before, after, "a stubbed run wrote into the real benchruns store")


class CostCeilingStopTests(unittest.TestCase):
    """PLAN D1 — the ceiling is re-checked before EVERY dispatch, and crossing it is a CLEAN
    outcome: exit 0, stated on stdout, remaining cells `skipped: cost-ceiling`, envelope
    labelled partial."""

    def _expensive_runner(self):
        # Reported usage far above the plan estimate -- exactly the case the per-dispatch
        # re-check exists for: the pre-run grand-total check passed, and reality did not.
        return make_stub_runner(usage={"input_tokens": 10_000_000_000, "output_tokens": 1})

    def test_actual_overspend_stops_the_run_before_the_next_dispatch(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            store = td / "store"
            ceiling = _grand_total(repo, ["haiku"], td / "plan-scratch") * 2 + 0.01
            runner = self._expensive_runner()
            args = _run_args(repo, store, "--live", "--max-usd", str(ceiling))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = rb.cmd_run(args, runner=runner)
            text = out.getvalue()

            self.assertEqual(rc, 0, "a ceiling stop is a clean outcome, not an error")
            self.assertIn("STOPPED: cost ceiling reached", text)
            self.assertEqual(len(runner.calls), 1, "a second cell was dispatched over budget")

            rows, notes = rb.list_runs(store)
            results = json.loads((Path(rows[0]["path"]) / "results.json").read_text())
            skipped = [c for c in results["cells"] if c["skipped"]]
            self.assertTrue(skipped)
            for cell in skipped:
                self.assertEqual(cell["skipped"], "cost-ceiling")
                self.assertIsNone(cell["usd"])
                self.assertIsNone(cell["patch"])
            self.assertIn(rb.COST_CEILING_LABEL, results["labels"])
            self.assertTrue(any("cost ceiling reached" in n for n in results["notes"]))
            self.assertAlmostEqual(results["spend"]["ceiling_usd"], ceiling)

    def test_a_non_finite_ceiling_never_reaches_the_dispatch_loop(self):
        # The T4 post-mortem, one layer deeper: `--max-usd nan` must not merely exit 2, it
        # must exit 2 with the runner untouched.
        for bad in ("nan", "inf", "-inf", "-1"):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as td:
                td = Path(td)
                repo = td / "target"
                build_issue_fixture_repo(repo)
                store = td / "store"
                runner = make_stub_runner()
                args = rb.build_parser().parse_args([
                    "run", "--repo", str(repo), "--models", "haiku",
                    "--store-dir", str(store), "--live", f"--max-usd={bad}",
                ])
                with contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()), \
                        self.assertRaises(SystemExit) as ctx:
                    rb.cmd_run(args, runner=runner)
                self.assertEqual(ctx.exception.code, 2)
                self.assertEqual(runner.calls, [], f"--max-usd {bad} reached the dispatch loop")

    def test_the_ceiling_is_validated_once_per_cell(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            store = td / "store"
            ceiling = _grand_total(repo, ["haiku"], td / "plan-scratch") * 4 + 1.0
            args = _run_args(repo, store, "--live", "--max-usd", str(ceiling))
            with mock.patch.object(rb, "validate_ceiling", wraps=rb.validate_ceiling) as spy:
                with contextlib.redirect_stdout(io.StringIO()):
                    rb.cmd_run(args, runner=make_stub_runner())
            # once for the CLI gate + once per cell (2 mined tasks x 1 candidate)
            self.assertGreaterEqual(spy.call_count, 3, spy.call_args_list)

    def test_refusal_paths_from_t4_still_hold_with_a_runner_injected(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            store = td / "store"
            runner = make_stub_runner()
            for extra in ([], ["--live"], ["--live", "--max-usd", "0.0000001"]):
                with self.subTest(extra=extra):
                    args = _run_args(repo, store, *extra)
                    with contextlib.redirect_stdout(io.StringIO()), \
                            contextlib.redirect_stderr(io.StringIO()), \
                            self.assertRaises(SystemExit) as ctx:
                        rb.cmd_run(args, runner=runner)
                    self.assertEqual(ctx.exception.code, 2)
            self.assertEqual(runner.calls, [], "a refusal path still reached the runner")
            self.assertFalse(store.exists() and any(store.iterdir()))

    def test_a_ceiling_that_covers_cells_but_not_grades_stops_before_grading(self):
        # T7 item 5 / P2-F5: the ceiling must be re-checked before EVERY judge grade exactly
        # as it is before every candidate dispatch. This mirrors
        # `test_actual_overspend_stops_the_run_before_the_next_dispatch` above, one stage
        # later -- candidate dispatches stay cheap (their reported usage is tiny, well under
        # their plan estimate), but the FIRST judge grade reports usage far above its own
        # estimate, blowing through the ceiling before the second grade can be dispatched.
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            store = td / "store"

            card = rb.build_plan(repo, ["haiku"], scratch_dir=td / "plan-scratch")
            judge_id = card["judge"]
            self.assertGreaterEqual(len(card["tasks"]), 2, "need >=2 tasks for a partial stop")

            def runner(argv, cwd):
                (Path(cwd) / "candidate_fix.py").write_text("# cheap candidate work\n")
                idx = argv.index("--model")
                model = argv[idx + 1]
                if model == judge_id:
                    # A judge grade reporting usage wildly above its own JUDGE_GRADE_PROFILE
                    # estimate -- the actual-cost-blows-past-the-estimate case, at grading
                    # time instead of candidate-dispatch time.
                    payload = {
                        "type": "result", "subtype": "success",
                        "usage": {"input_tokens": 10_000_000_000, "output_tokens": 1},
                    }
                    return 0, json.dumps(payload) + "\nGRADE A=correct B=correct EQUIVALENT=yes"
                return 0, _canned_result_json({"input_tokens": 10, "output_tokens": 5})

            ceiling = card["totals"]["grand_total"] + 0.01
            args = _run_args(repo, store, "--live", "--max-usd", str(ceiling))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = rb.cmd_run(args, runner=runner)
            text = out.getvalue()

            self.assertEqual(rc, 0, "a ceiling stop mid-grading is still a clean outcome")
            self.assertIn("STOPPED: cost ceiling reached", text)

            rows, notes = rb.list_runs(store)
            results = json.loads((Path(rows[0]["path"]) / "results.json").read_text())

            # every candidate cell dispatched -- the ceiling only bit during grading.
            self.assertTrue(results["cells"], notes)
            self.assertTrue(all(not c["skipped"] for c in results["cells"]))

            skipped_grades = [g for g in results["grades"] if g["skipped"]]
            dispatched_grades = [g for g in results["grades"] if not g["skipped"]]
            self.assertTrue(dispatched_grades, "the first grade should have been dispatched")
            self.assertTrue(skipped_grades, "a later grade should have been skipped")
            for g in skipped_grades:
                self.assertEqual(g["skipped"], "cost-ceiling")
                self.assertIsNone(g["grade"])
                self.assertIsNone(g["usd"])
                self.assertIsNone(g["usd_basis"])
            self.assertIn(rb.COST_CEILING_LABEL, results["labels"])
            self.assertTrue(
                any("before grading every cell" in n for n in results["notes"]), results["notes"]
            )

            # F5 (Phase 3 review): the STOPPED line's counters counted CELLS only, so a stop
            # that cut every remaining GRADE announced itself as "0 skipped". The envelope was
            # honest; the line the user actually reads was not.
            self.assertRegex(
                text,
                r"\d+ judge grade\(s\) dispatched, [1-9]\d* skipped \(cost-ceiling\)",
                f"the stop line does not account for skipped judge grades:\n{text}",
            )


class DemoRunTests(unittest.TestCase):
    def test_demo_runs_the_stubbed_loop_and_reports_where_results_landed(self):
        store = rb.DEFAULT_STORE_DIR
        before = sorted(p.name for p in store.iterdir()) if store.is_dir() else None

        out = io.StringIO()
        with mock.patch.object(rb, "default_dispatch_runner", _explode_runner):
            with contextlib.redirect_stdout(out):
                rb.main(["demo"])
        text = out.getvalue()

        after = sorted(p.name for p in store.iterdir()) if store.is_dir() else None
        self.assertEqual(before, after, "demo wrote into the real benchruns store")

        self.assertIn("## matrix", text)
        self.assertIn("results.json:", text)
        # T8 widened the demo to the FULL pipeline: two candidates x two mined tasks, so the
        # cell count this line used to pin (1) is no longer the demo's shape. The property
        # being asserted is unchanged -- the stubbed loop ran to completion and said so.
        self.assertRegex(text, r"completed: \d+ cell\(s\) dispatched")
        self.assertIn("0 real binaries invoked", text)
        self.assertIn("--output-format json: True", text)
        self.assertNotIn("MUTATED", text)


# ---------------------------------------------------------------------------------------------
# T5R — Phase 2 remediation. Everything below is still offline and free: fixture repos in temp
# dirs, injected dispatch runners, and — where a stub would hide the defect on purpose — a
# local `sys.executable` command that runs stdlib-only code inside a sandbox we built.


def _solution_needles(task):
    """Strings that exist ONLY in solution material for `task`.

    The added lines of its `reference_patch` (the fix's own content) and the withheld
    fix-commit test blobs — the two things PLAN R2 says a candidate must never see. Lines
    shorter than 8 characters are dropped: a needle has to be discriminating, not merely
    present somewhere.
    """
    needles = []
    for line in (task.get("reference_patch") or "").splitlines():
        if line.startswith("+++") or not line.startswith("+"):
            continue
        body = line[1:].strip()
        if len(body) >= 8:
            needles.append(body)
    for blob in (task.get("test_blobs") or {}).values():
        for line in blob.splitlines():
            body = line.strip()
            if len(body) >= 8:
                needles.append(body)
    return sorted(set(needles))


def _the_run_dir(store):
    """The single run dir under a test store — resolved mid-run, from the store the test owns."""
    dirs = [p for p in Path(store).iterdir() if p.is_dir()]
    assert len(dirs) == 1, f"expected exactly one run dir under {store}: {dirs}"
    return dirs[0]


def _inspect_ancestry(cwd, needles, run_dir=None):
    """What a live dispatch sitting in `cwd` can reach by walking `..` -> an observation dict.

    A candidate's cwd is `<run-dir>/work/cell-NNN`, so the run dir is its grandparent, and
    walking that recursively IS "every ancestor directory up to and including the run dir",
    plus everything those directories hold: a sibling cell sandbox, a mining scratch site,
    `tasks/`, `dispatches/`, a stray setup patch. The dispatching directory's own subtree is
    excluded when it lies inside — a candidate's sandbox legitimately holds the repo at its
    buggy base state, and `test_mined_task_records_land_in_the_store_never_in_the_sandbox`
    covers what may not be inside it.

    T7R/F1: `run_dir` may be passed explicitly so the SAME hunt covers a dispatch whose cwd is
    NOT under the run dir at all — the judge. For that dispatch the two properties are (a) the
    run dir is not an ancestor, so `..` reaches none of it (`under_run_dir`), and (b) the run
    dir holds no solution material anyway while any dispatch is live, which is what the rest
    of this observation measures.

    Files are read as bytes and decoded loosely: a git object store is binary, and a leak
    hunt must not die on it. File NAMES are hunted too — `dispatches/<task>__<model>.json`
    names the candidate model in its filename, not only in its content.
    """
    cwd = Path(cwd).resolve()
    run_dir = Path(run_dir).resolve() if run_dir is not None else cwd.parents[1]
    under_run_dir = cwd == run_dir or run_dir in cwd.parents
    hits, scanned = [], 0
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file():
            continue
        if under_run_dir and (path == cwd or cwd in path.parents):
            continue
        scanned += 1
        text = path.read_bytes().decode("utf-8", "ignore")
        for needle in needles:
            if needle in text:
                hits.append(f"{path.relative_to(run_dir)} contains {needle!r}")
            if needle in path.name:
                hits.append(f"{path.relative_to(run_dir)} is NAMED for {needle!r}")
    return {
        "hits": hits,
        "scanned": scanned,
        "cwd": str(cwd),
        "is_cell": cwd.name.startswith("cell-"),
        "under_run_dir": under_run_dir,
        "run_dir": str(run_dir),
        "sites": sorted(
            str(p.relative_to(run_dir)) for p in run_dir.rglob("site-*") if p.is_dir()
        ),
        "setup_patches": sorted(str(p.relative_to(run_dir)) for p in run_dir.rglob("*.patch")),
        # T20: the full-patch DIAGNOSTIC's substrate carries the candidate's WHOLE patch and
        # the withheld `test_blobs`, and it is built under `<run-dir>/work` — one `../` from
        # the next candidate's cwd. Its LIFETIME is the property: it must not exist while any
        # dispatch is live. (Its own `TemporaryDirectory` is what enforces that; this is the
        # check that would notice if someone ever hoisted it out of the `with`.)
        "grade_substrates": sorted(
            str(p.relative_to(run_dir))
            for p in run_dir.rglob("repo-bench-fullpatch-*")
        ) + sorted(
            str(p.relative_to(run_dir)) for p in run_dir.rglob("repo-bench-grade-*")
        ),
        "task_files": sorted(str(p.relative_to(run_dir)) for p in (run_dir / "tasks").glob("*")),
        "dispatch_files": sorted(
            str(p.relative_to(run_dir)) for p in (run_dir / "dispatches").glob("*")
        ),
        # T5R2: `plan.json` lists every task, and a general-mode task id is `mut-N-<stem>` --
        # `cat ../../plan.json` narrows the hunt to one file with every other fix in place.
        "plan_files": sorted(str(p.relative_to(run_dir)) for p in run_dir.glob("plan.json")),
    }


def _sandbox_git(cell_dir, *args):
    """Raw git against a candidate's own sandbox -> loosely-decoded output.

    Bytes, not `text=True`: `cat-file --batch-all-objects --batch` streams raw blob content
    and a leak hunt must not die on one non-UTF-8 byte.
    """
    proc = subprocess.run(["git", "-C", str(cell_dir), *args], capture_output=True)
    return (proc.stdout + proc.stderr).decode("utf-8", "ignore")


def _inspect_sandbox_history(cell_dir, needles):
    """What the candidate's OWN git hands it — the one place `_inspect_ancestry` never looks.

    `_inspect_ancestry` deliberately excludes the cell dir: it legitimately holds the repo at
    its buggy base state. But a sandbox built with the setup patch as a SECOND commit hands
    the candidate `git diff HEAD~1 HEAD`, reversed — the general-mode answer, from inside its
    own cwd. Three surfaces, because closing one still leaves the others: the commit graph
    (`log -p`), the reflog (`HEAD@{1}` survives an `--amend`), and the object store itself (a
    pre-amend commit stays readable via `fsck`/`cat-file` until it is pruned).
    """
    cell_dir = Path(cell_dir)
    log_p = _sandbox_git(cell_dir, "log", "-p")
    objects = _sandbox_git(cell_dir, "cat-file", "--batch-all-objects", "--batch")
    return {
        "commits": _sandbox_git(cell_dir, "rev-list", "--count", "HEAD").strip(),
        "log_hits": sorted({n for n in needles if n in log_p}),
        "log_diffs": [line for line in log_p.splitlines() if line.startswith("diff --git")],
        "reflog": [
            line for line in _sandbox_git(cell_dir, "reflog").splitlines() if line.strip()
        ],
        "object_hits": sorted({n for n in needles if n in objects}),
    }


def _mutated_paths(task):
    """The file a general-mode task mutated, as path AND stem — both name it.

    Read off the setup patch's own `+++ b/<path>` header rather than parsed out of the task
    id, so this stays a fact about the patch and not a restatement of the id format.
    """
    names = set()
    for line in (task.get("setup_patch") or "").splitlines():
        if line.startswith("+++ b/"):
            path = line[len("+++ b/"):].strip()
            if path:
                names.add(path)
                names.add(Path(path).stem)
    return sorted(names)


#: Written into every cell sandbox by the leak-hunting runner below, and hunted for on every
#: LATER dispatch: one candidate reading another's captured work is cross-candidate
#: contamination, not just an inconvenience.
CANDIDATE_WORK_MARKER = "MARKER-CANDIDATE-WORK-9f3a"


def _candidate_model_ids(words=("haiku", "sonnet")):
    """The real model ids the ancestry tests' `--models` resolve to — RESOLVED at run time
    through the same `claude_execute.resolve_model` seam the engine uses, never written down
    here (no real model ids in tests, kit-wide).

    T7R/F1 hunts for these too: `dispatches/<task_id>__<model>.json` tells a judge which model
    produced the patch in the other slot, which is half of what D6's blind slots hide.
    """
    pricing = rb._cr().load_pricing()
    return [rb._ce().resolve_model(pricing, w) for w in words]


class SolutionAncestryTests(unittest.TestCase):
    """F1 (Phase 2 review) — THE measurement-validity property: while ANY dispatch is live,
    nothing in the candidate's ANCESTRY holds solution material.

    A candidate runs with `cwd=<run-dir>/work/cell-NNN` and permissions bypassed, so an
    ordinary `cat` reached `../<task_id>.setup.patch` (reverse it — that is the general-mode
    answer), `../site-N/` (a mining scratch sandbox), `../../tasks/<task_id>.json`
    (`reference_patch` AND `test_blobs`, in BOTH modes) and `../../dispatches/*.json` (an
    earlier candidate's captured patch). PLAN D3's "unreachable by construction" was a
    statement about git HISTORY and was never true of the filesystem.

    The old proxy — "no test blob inside the cell dir" — passed the entire time the reference
    patch sat one `../` away, which is why it is KEPT and this was added beside it. Every
    measurement this tool makes is worthless if a candidate can read the answer.
    """

    def _leak_hunting_runner(self, needles, observations, store):
        """T7R/F1: hunts on EVERY dispatch — candidate and judge alike.

        T7 excluded the judge's cwd here, reasoning that the judge is DESIGNED to see both
        patches (PLAN D6, that is grading). True, and beside the point: seeing both patches is
        grading; knowing WHICH is the reference — and which model wrote the other one — is
        exactly the bias control D6 exists to protect, and the judge could read both facts off
        `../../tasks/` and `../../dispatches/`. The needles include the candidate model ids
        for that reason.
        """
        def runner(argv, cwd):
            hunted = list(needles)
            if observations:  # a later dispatch also hunts for earlier candidates' work
                hunted.append(CANDIDATE_WORK_MARKER)
            observations.append(_inspect_ancestry(cwd, hunted, run_dir=_the_run_dir(store)))
            if Path(cwd).name.startswith("cell-"):
                (Path(cwd) / "candidate_fix.py").write_text(CANDIDATE_WORK_MARKER + "\n")
            return 0, _canned_result_json()

        return runner

    def _assert_clean(self, observations, expected_dispatches):
        self.assertEqual(
            len(observations), expected_dispatches,
            "the leak hunt did not run on every dispatch",
        )
        judge_dispatches = [obs for obs in observations if not obs["is_cell"]]
        self.assertTrue(
            judge_dispatches,
            "no judge dispatch was inspected — the hunt must cover EVERY dispatch cwd (F1)",
        )
        for obs in observations:
            self.assertGreater(
                obs["scanned"], 0,
                "nothing was scanned — the ancestry walk proved nothing",
            )
            self.assertEqual(obs["hits"], [], f"SOLUTION LEAK in the dispatch's ancestry: {obs}")
            self.assertEqual(obs["sites"], [], f"a mining scratch sandbox was live: {obs}")
            self.assertEqual(obs["setup_patches"], [], f"a setup patch was reachable: {obs}")
            self.assertEqual(obs["task_files"], [], f"tasks/ was populated mid-run: {obs}")
            self.assertEqual(obs["dispatch_files"], [], f"dispatches/ was populated mid-run: {obs}")
            self.assertEqual(obs["plan_files"], [], f"plan.json was readable mid-run: {obs}")
            self.assertEqual(
                obs["grade_substrates"], [],
                f"a grade substrate (in-scope or T20 diagnostic) was live: {obs}",
            )
        for obs in judge_dispatches:
            self.assertFalse(
                obs["under_run_dir"],
                f"the judge dispatched from INSIDE the run dir — `..` reaches the store: {obs}",
            )

    def test_issue_replay_ancestry_holds_no_reference_patch_or_test_blob(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            store = td / "store"

            tasks, _notes = rb.mine_issue_tasks(repo, gh_runner=None)
            needles = sorted(
                {n for t in tasks for n in _solution_needles(t)} | set(_candidate_model_ids())
            )
            self.assertTrue(needles, "the fixture yielded no solution material to hunt for")
            self.assertTrue(any(t["test_blobs"] for t in tasks))

            observations = []
            args = rb.build_parser().parse_args([
                "run", "--repo", str(repo), "--models", "haiku,sonnet",
                "--store-dir", str(store), "--live", "--max-usd", "1000000",
            ])
            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_run(args, runner=self._leak_hunting_runner(needles, observations, store))

            # 2 tasks x 2 candidates = 4 cells, and one judge grade per cell (PLAN D6).
            self._assert_clean(observations, expected_dispatches=len(tasks) * 2 * 2)

            # …and the store still holds everything grading needs, written after the loop.
            run_dir = Path(rb.list_runs(store)[0][0]["path"])
            stored = [json.loads(p.read_text()) for p in (run_dir / "tasks").glob("*.json")]
            self.assertEqual(len(stored), len(tasks))
            self.assertTrue(any(b["reference_patch"] for b in stored))
            self.assertEqual(len(list((run_dir / "dispatches").glob("*.json"))), len(tasks) * 2)

    def test_general_mode_ancestry_holds_no_reference_patch_or_setup_patch(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            head, _ = build_parity_fixture_repo(repo)
            store = td / "store"

            tasks, _notes = rb.mine_general_tasks(
                repo, head, test_cmd="run-tests", test_runner=_ge_marker_runner,
                scratch_dir=td / "scratch",
            )
            needles = sorted(
                {n for t in tasks for n in _solution_needles(t)} | set(_candidate_model_ids())
            )
            self.assertTrue(needles, "the fixture yielded no solution material to hunt for")

            observations = []
            args = rb.build_parser().parse_args([
                "run", "--repo", str(repo), "--models", "haiku,sonnet", "--mode", "general",
                "--test-cmd", "run-tests", "--store-dir", str(store),
                "--live", "--max-usd", "1000000",
            ])
            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_run(
                    args,
                    runner=self._leak_hunting_runner(needles, observations, store),
                    test_runner=_ge_marker_runner,
                )

            self._assert_clean(observations, expected_dispatches=len(tasks) * 2 * 2)

    def test_general_mode_ancestry_never_names_the_mutated_file(self):
        """T5R2 — `plan.json`. Task ids are `mut-N-<stem>`, so a plan card sitting two `../`s
        up narrows a whole-repo hunt to ONE file even with every other ancestry fix in place:
        the candidate no longer has to find the bug, only to read the file the harness names.
        It is buffered with `tasks/` and `dispatches/` now and written after the loop."""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            head, _ = build_parity_fixture_repo(repo)
            store = td / "store"

            tasks, _notes = rb.mine_general_tasks(
                repo, head, test_cmd="run-tests", test_runner=_ge_marker_runner,
                scratch_dir=td / "scratch",
            )
            needles = sorted({n for t in tasks for n in _mutated_paths(t)})
            self.assertTrue(needles, "the fixture named no mutated file to hunt for")

            observations = []
            args = rb.build_parser().parse_args([
                "run", "--repo", str(repo), "--models", "haiku,sonnet", "--mode", "general",
                "--test-cmd", "run-tests", "--store-dir", str(store),
                "--live", "--max-usd", "1000000",
            ])
            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_run(
                    args,
                    runner=self._leak_hunting_runner(needles, observations, store),
                    test_runner=_ge_marker_runner,
                )

            self._assert_clean(observations, expected_dispatches=len(tasks) * 2 * 2)

            # …and the plan card still lands in the store once no dispatch is live.
            run_dir = Path(rb.list_runs(store)[0][0]["path"])
            card = json.loads((run_dir / "plan.json").read_text())
            self.assertEqual(card["mode"], "general")
            self.assertTrue(card["tasks"])

    def test_general_mode_cell_sandbox_history_holds_no_answer_mid_dispatch(self):
        """T5R2 — the same single-root property, asserted where it actually matters: inside
        the sandbox a live dispatch is running in, on every cell of a real `run`."""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            head, _ = build_parity_fixture_repo(repo)
            store = td / "store"

            tasks, _notes = rb.mine_general_tasks(
                repo, head, test_cmd="run-tests", test_runner=_ge_marker_runner,
                scratch_dir=td / "scratch",
            )
            needles = sorted({n for t in tasks for n in _solution_needles(t)})
            self.assertTrue(needles, "the fixture yielded no solution material to hunt for")

            observations = []

            def runner(argv, cwd):
                # T7: the SAME injected runner also carries judge-grading dispatches now, in
                # a bare scratch `cwd` that is never a git sandbox at all -- `git log -p`
                # against it proves nothing about THIS probe (sandbox commit-graph history),
                # so only a real candidate sandbox (has `.git`) is inspected here.
                if (Path(cwd) / ".git").exists():
                    observations.append(_inspect_sandbox_history(cwd, needles))
                return 0, _canned_result_json()

            args = rb.build_parser().parse_args([
                "run", "--repo", str(repo), "--models", "haiku,sonnet", "--mode", "general",
                "--test-cmd", "run-tests", "--store-dir", str(store),
                "--live", "--max-usd", "1000000",
            ])
            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_run(args, runner=runner, test_runner=_ge_marker_runner)

            self.assertEqual(
                len(observations), len(tasks) * 2, "the history hunt did not run on every cell"
            )
            for obs in observations:
                self.assertEqual(obs["commits"], "1", f"sandbox history is mineable: {obs}")
                self.assertEqual(obs["log_hits"], [], f"the fix is readable in `git log`: {obs}")
                self.assertEqual(obs["log_diffs"], [], f"a diff was left to mine: {obs}")
                self.assertEqual(obs["reflog"], [], f"the reflog survived the amend: {obs}")
                self.assertEqual(
                    obs["object_hits"], [], f"a dangling object holds the clean source: {obs}"
                )


def build_artifact_fixture_repo(root):
    """A repo whose REAL test command leaves artifacts behind — the shape of every Python
    project, and the one thing a stub test runner can never imitate. One mutation site."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    (root / "calc.py").write_text(
        "def classify(x):\n"
        "    if x >= 10:\n"
        "        return \"big\"\n"
        "    return \"small\"\n"
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "c1: classify")
    return _git(root, "rev-parse", "HEAD").strip()


#: A REAL test command: local, offline, stdlib-only, free, and run only inside a sandbox this
#: suite built. It imports `calc` (so CPython drops `__pycache__/calc.*.pyc` beside it) AND
#: writes a binary file outright, so the artifact exists no matter how the ambient environment
#: feels about bytecode. RED exactly when the `>=` site has been flipped.
ARTIFACT_TEST_CMD = f"{shlex.quote(sys.executable)} -c " + shlex.quote(
    "import calc\n"
    "open('build.artifact', 'wb').write(bytes(range(256)))\n"
    "assert calc.classify(10) == 'big'\n"
)


class GeneralModeArtifactTests(unittest.TestCase):
    """F2 (Phase 2 review) — general mode used to die on any repo whose tests produce
    artifacts, i.e. every Python repo: `git add -A` after the red check swept `__pycache__`
    into the mutated commit, both patches picked up binary hunks with no full index line, and
    `prepare_cell_sandbox`'s `git apply` failed out of the loop into exit 2.

    EVERY general-mode test before this one injects a stub `test_runner` that executes
    nothing, so no artifact was ever created and the whole class was invisible. These use the
    real thing.
    """

    def test_the_test_command_really_produces_artifacts(self):
        # Vacuity guard: if this command left the sandbox clean, everything below would pass
        # for the wrong reason.
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            head = build_artifact_fixture_repo(repo)
            info = rb.make_sandbox(repo, head, td / "sandbox")
            sandbox = Path(info["path"])
            rc, out = rb.default_test_runner(ARTIFACT_TEST_CMD, str(sandbox))
            self.assertEqual(rc, 0, out)
            self.assertTrue((sandbox / "build.artifact").exists(), "no artifact was produced")
            self.assertNotEqual(
                _git(sandbox, "status", "--porcelain"), "",
                "the test command left the sandbox pristine — it cannot exercise F2",
            )

    def test_mined_patches_carry_the_mutated_file_and_nothing_else(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            head = build_artifact_fixture_repo(repo)
            tasks, notes = rb.mine_general_tasks(
                repo, head, limit=1, test_cmd=ARTIFACT_TEST_CMD, scratch_dir=td / "scratch",
            )
            self.assertEqual(len(tasks), 1, notes)
            task = tasks[0]
            for name in ("setup_patch", "reference_patch"):
                patch = task[name]
                with self.subTest(patch=name):
                    self.assertIn("calc.py", patch)
                    self.assertNotIn("build.artifact", patch)
                    self.assertNotIn("__pycache__", patch)
                    self.assertNotIn("Binary files", patch)
            # the artifacts also never reached `_changed_loc` -> `size_profile` -> the estimate
            self.assertEqual(task["size_profile"], "XS")

    def test_a_general_mode_run_completes_with_an_artifact_producing_test_command(self):
        # The end-to-end reproduction: no `test_runner` injected, so red-validation runs the
        # real command; the DISPATCH runner is still a stub, as it is everywhere in this file.
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_artifact_fixture_repo(repo)
            store = td / "store"
            out = io.StringIO()
            args = rb.build_parser().parse_args([
                "run", "--repo", str(repo), "--models", "haiku", "--mode", "general",
                "--test-cmd", ARTIFACT_TEST_CMD, "--limit", "1", "--store-dir", str(store),
                "--live", "--max-usd", "1000000",
            ])
            with contextlib.redirect_stdout(out):
                rc = rb.cmd_run(args, runner=make_stub_runner())
            self.assertEqual(rc, 0)
            self.assertIn("completed: 1 cell(s) dispatched", out.getvalue())

            rows, notes = rb.list_runs(store)
            results = json.loads((Path(rows[0]["path"]) / "results.json").read_text())
            self.assertEqual(results["mode"], "general")
            self.assertEqual(len(results["cells"]), 1)
            self.assertIsNone(results["cells"][0]["skipped"])


class AdapterPricingLoaderTests(unittest.TestCase):
    """F4 (Phase 2 review) — PLAN D2 pins the adapter contract as `name`, `build_argv`,
    `extract_usage` and a PRICING LOADER. With the loader missing and
    `_cr().load_pricing()` hardwired into the dispatch path, a codex/copilot adapter would
    have been priced out of Claude's pricing file unless those functions were edited — which
    is not "drops in"."""

    def _stub_adapter(self, calls):
        return {
            "name": "stub-harness",
            "build_argv": rb.build_claude_argv,
            "extract_usage": rb.extract_usage,
            "load_pricing": lambda: (calls.append("load_pricing"), FIXTURE_PRICING)[1],
        }

    def test_the_claude_adapter_carries_a_pricing_loader(self):
        self.assertTrue(callable(rb.CLAUDE_ADAPTER["load_pricing"]))
        self.assertEqual(
            rb.CLAUDE_ADAPTER["load_pricing"](), _load("cost_report").load_pricing()
        )

    def test_dispatch_cell_prices_through_the_adapter(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            tasks, _ = rb.mine_issue_tasks(repo, gh_runner=None)
            task = tasks[0]
            info, baseline = rb.prepare_cell_sandbox(task, repo, td / "cell")

            calls = []
            record = rb.dispatch_cell(
                task, "fake-haiku-1", self._stub_adapter(calls), info["path"],
                runner=make_stub_runner(), claude_bin="stub-bin", pricing=None,
                estimated_usd=0.25, baseline_commit=baseline,
            )
            self.assertEqual(calls, ["load_pricing"])
            self.assertEqual(record["usd_basis"], "actual")
            self.assertAlmostEqual(
                record["usd"], rb.price_usage("fake-haiku-1", STUB_USAGE, FIXTURE_PRICING)
            )

    def test_cmd_run_loads_its_pricing_through_the_adapter(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            store = td / "store"
            calls = []
            adapter = dict(rb.CLAUDE_ADAPTER)
            adapter["load_pricing"] = lambda: (
                calls.append("load_pricing"), rb.CLAUDE_ADAPTER["load_pricing"]()
            )[1]
            args = _run_args(repo, store, "--live", "--max-usd", "1000000")
            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_run(args, runner=make_stub_runner(), adapter=adapter)
            self.assertEqual(
                calls, ["load_pricing"],
                "cmd_run priced the run from a hardwired loader, not from the adapter",
            )


class EnvelopeAlwaysWrittenTests(unittest.TestCase):
    """F6 (Phase 2 review) — an exception inside the dispatch loop used to skip the
    `results.json` write entirely, leaving a run with no envelope: no spend, no basis, no
    labels. That is the ONE artifact PLAN D8 says must always carry the honesty labels."""

    def test_a_mid_loop_exception_still_writes_a_labelled_envelope(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            store = td / "store"

            calls = []

            def exploding_runner(argv, cwd):
                calls.append(cwd)
                if len(calls) >= 2:
                    raise RuntimeError("the harness died mid-run")
                (Path(cwd) / "candidate_fix.py").write_text("# work\n")
                return 0, _canned_result_json()

            args = _run_args(repo, store, "--live", "--max-usd", "1000000")
            with contextlib.redirect_stdout(io.StringIO()), \
                    self.assertRaises(RuntimeError):
                rb.cmd_run(args, runner=exploding_runner)

            rows, notes = rb.list_runs(store)
            self.assertEqual(len(rows), 1, notes)
            run_dir = Path(rows[0]["path"])
            results_path = run_dir / "results.json"
            self.assertTrue(results_path.exists(), "the aborted run left no envelope at all")
            results = json.loads(results_path.read_text())

            self.assertEqual(len(results["cells"]), 1, "the completed cell was lost")
            self.assertEqual(results["cells"][0]["usd_basis"], "actual")
            self.assertIn(rb.ABORTED_LABEL, results["labels"])
            self.assertIn(rb.ABORTED_NOTE, results["notes"])
            self.assertIn(rb.SPEND_BASIS_LABELS[results["spend"]["basis"]], results["labels"])
            self.assertGreater(results["spend"]["spent_usd"], 0.0)
            # grading's inputs were flushed too — the finally writes them, not the happy path
            self.assertTrue(list((run_dir / "tasks").glob("*.json")))
            self.assertEqual(len(list((run_dir / "dispatches").glob("*.json"))), 1)

    def test_a_completed_run_is_never_labelled_aborted(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            store = td / "store"
            args = _run_args(repo, store, "--live", "--max-usd", "1000000")
            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_run(args, runner=make_stub_runner())
            results = json.loads(
                (Path(rb.list_runs(store)[0][0]["path"]) / "results.json").read_text()
            )
            self.assertNotIn(rb.ABORTED_LABEL, results["labels"])


class OverspendLabelTests(unittest.TestCase):
    """F3 (Phase 2 review) — recorded spend CAN exceed the ceiling: a dispatch's real cost is
    unknown until it returns, so the pre-dispatch projection stops the NEXT one and cannot
    refund the last. The overshoot is unavoidable; rendering it identically to a clean
    preventive stop is the drift GUARDRAILS names ("a dollar figure printed without a basis
    or label beside it")."""

    def test_an_overshoot_is_labelled_and_the_stop_line_carries_its_basis(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            store = td / "store"
            ceiling = _grand_total(repo, ["haiku"], td / "plan-scratch") * 2 + 0.01
            runner = make_stub_runner(usage={"input_tokens": 10_000_000_000, "output_tokens": 1})
            args = _run_args(repo, store, "--live", "--max-usd", str(ceiling))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rb.cmd_run(args, runner=runner)
            text = out.getvalue()

            results = json.loads(
                (Path(rb.list_runs(store)[0][0]["path"]) / "results.json").read_text()
            )
            spend = results["spend"]
            self.assertGreater(
                spend["spent_usd"], spend["ceiling_usd"],
                "this test no longer produces an overshoot — it proves nothing",
            )
            self.assertTrue(
                any(l.startswith(rb.OVERSPEND_LABEL_PREFIX) for l in results["labels"]),
                f"an overshoot went unlabelled: {results['labels']}",
            )
            self.assertIn(rb.COST_CEILING_LABEL, results["labels"])
            self.assertIn("STOPPED: cost ceiling reached", text)
            self.assertIn(
                rb.SPEND_BASIS_LABELS[spend["basis"]], text,
                "the STOPPED branch printed dollars without their basis (the completed "
                "branch already carried it — that asymmetry IS the drift signal)",
            )
            self.assertIn(rb.OVERSPEND_LABEL_PREFIX, text)

    def test_a_run_inside_its_ceiling_carries_no_overspend_label(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            store = td / "store"
            args = _run_args(repo, store, "--live", "--max-usd", "1000000")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rb.cmd_run(args, runner=make_stub_runner())
            results = json.loads(
                (Path(rb.list_runs(store)[0][0]["path"]) / "results.json").read_text()
            )
            self.assertLess(results["spend"]["spent_usd"], results["spend"]["ceiling_usd"])
            self.assertFalse(
                [l for l in results["labels"] if l.startswith(rb.OVERSPEND_LABEL_PREFIX)]
            )
            self.assertNotIn(rb.OVERSPEND_LABEL_PREFIX, out.getvalue())


class KeepWorkWarningTests(unittest.TestCase):
    """F1 (Phase 2 review) — cell sandboxes are swept the moment their patch is captured, so
    one candidate cannot read another's work out of a sibling directory. `--keep-work` turns
    that off; it must say so, loudly, rather than quietly becoming a measurement condition."""

    def _run(self, td, *extra):
        td = Path(td)
        repo = td / "target"
        build_issue_fixture_repo(repo)
        store = td / "store"
        args = _run_args(repo, store, "--live", "--max-usd", "1000000", *extra)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rb.cmd_run(args, runner=make_stub_runner())
        results = json.loads(
            (Path(rb.list_runs(store)[0][0]["path"]) / "results.json").read_text()
        )
        return out.getvalue(), results

    def test_keep_work_warns_on_stdout_and_in_the_envelope(self):
        with tempfile.TemporaryDirectory() as td:
            text, results = self._run(td, "--keep-work")
            self.assertIn(rb.KEEP_WORK_WARNING, text)
            self.assertIn(rb.KEEP_WORK_WARNING, results["notes"])
            self.assertIn("never for a measurement run", rb.KEEP_WORK_WARNING)

    def test_a_swept_run_carries_no_such_warning(self):
        with tempfile.TemporaryDirectory() as td:
            text, results = self._run(td)
            self.assertNotIn(rb.KEEP_WORK_WARNING, text)
            self.assertNotIn(rb.KEEP_WORK_WARNING, results["notes"])


# ---------------------------------------------------------------------------------------------
# T6 — oracles (a) tests and (b) structural similarity (PLAN D5), plus the P1-F5 + Nit strip.


class DiffParsingHelperTests(unittest.TestCase):
    """`_split_diff_by_file`/`_strip_test_hunks` are stdlib string parsing over a unified
    diff -- no external diff lib (PLAN D5/T6)."""

    def test_split_diff_by_file_with_git_headers(self):
        patch = (
            "diff --git a/src/a.py b/src/a.py\n"
            "index 111..222 100644\n"
            "--- a/src/a.py\n"
            "+++ b/src/a.py\n"
            "@@ -1 +1 @@\n-x = 1\n+x = 2\n"
            "diff --git a/tests/test_a.py b/tests/test_a.py\n"
            "index 333..444 100644\n"
            "--- a/tests/test_a.py\n"
            "+++ b/tests/test_a.py\n"
            "@@ -1 +1 @@\n-assert x == 1\n+assert x == 2\n"
        )
        blocks = rb._split_diff_by_file(patch)
        self.assertEqual([p for p, _ in blocks], ["src/a.py", "tests/test_a.py"])

    def test_split_diff_by_file_without_a_git_git_header(self):
        patch = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n"
        blocks = rb._split_diff_by_file(patch)
        self.assertEqual([p for p, _ in blocks], ["x.py"])

    def test_strip_removes_only_test_pattern_files(self):
        patch = (
            "--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
            "--- a/tests/test_a.py\n+++ b/tests/test_a.py\n@@ -1 +1 @@\n-y\n+z\n"
        )
        stripped = rb._strip_test_hunks(patch)
        self.assertIn("src/a.py", stripped)
        self.assertNotIn("tests/test_a.py", stripped)
        self.assertNotIn("+z", stripped)

    def test_strip_is_a_no_op_when_nothing_matches(self):
        patch = "--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
        self.assertEqual(rb._strip_test_hunks(patch), patch)

    def test_strip_of_a_deleted_test_file_resolves_the_path_from_the_minus_line(self):
        patch = "--- a/tests/test_gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-assert True\n"
        self.assertEqual(rb._strip_test_hunks(patch), "")

    def test_disabling_test_patterns_strips_nothing(self):
        patch = (
            "--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
            "--- a/tests/test_a.py\n+++ b/tests/test_a.py\n@@ -1 +1 @@\n-y\n+z\n"
        )
        self.assertEqual(rb._strip_test_hunks(patch, test_patterns=()), patch)


class OracleStructuralTests(unittest.TestCase):
    """Oracle (b): always available, SIMILARITY only, never correctness (PLAN D5)."""

    REF = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a = 1\n+a = 2\n"

    def test_label_is_mandatory_even_on_empty_inputs(self):
        r = rb.oracle_structural("", "")
        self.assertEqual(r["label"], rb.STRUCTURAL_LABEL)
        self.assertEqual(r["oracle"], "structural")

    def test_identical_patches_score_1_0_across_every_metric(self):
        same = rb.oracle_structural(self.REF, self.REF)
        self.assertEqual(same["files_jaccard"], 1.0)
        self.assertEqual(same["hunk_overlap"], 1.0)
        self.assertEqual(same["loc_delta_ratio"], 1.0)
        self.assertEqual(same["out_of_scope_files"], 0)
        self.assertEqual(same["label"], rb.STRUCTURAL_LABEL)

    def test_disjoint_patches_score_0_0(self):
        other = "--- a/y.py\n+++ b/y.py\n@@ -1 +1 @@\n-b\n+c\n"
        result = rb.oracle_structural(self.REF, other)
        self.assertEqual(result["files_jaccard"], 0.0)
        self.assertEqual(result["hunk_overlap"], 0.0)
        self.assertEqual(result["out_of_scope_files"], 1)

    def test_empty_candidate_is_all_zero_with_a_note_and_still_carries_the_label(self):
        result = rb.oracle_structural(self.REF, "")
        self.assertEqual(result["files_jaccard"], 0.0)
        self.assertEqual(result["hunk_overlap"], 0.0)
        self.assertEqual(result["loc_delta_ratio"], 0.0)
        self.assertEqual(result["out_of_scope_files"], 0)
        self.assertEqual(result["notes"], "candidate produced no change")
        self.assertEqual(result["label"], rb.STRUCTURAL_LABEL)

    def test_strip_keeps_a_source_only_correct_fix_from_being_depressed_by_the_test_hunk(self):
        """P1-F5 + Nit: `reference_patch` is the FULL fix diff and carries the fix commit's
        own test hunk -- a file the candidate structurally cannot produce, because that exact
        blob is withheld from its sandbox. Stripped (the default), a candidate that correctly
        fixes ONLY the source scores materially higher than it would against the unstripped
        reference (`test_patterns=()` disables the strip, standing in for "unstripped")."""
        reference_patch = (
            "--- a/m.py\n+++ b/m.py\n@@ -1,2 +1,2 @@\n"
            "-def f():\n-    return 1\n+def f():\n+    return 2\n"
            "--- a/tests/test_m.py\n+++ b/tests/test_m.py\n@@ -0,0 +1,2 @@\n"
            "+import m\n+assert m.f() == 2\n"
        )
        candidate_patch = (
            "--- a/m.py\n+++ b/m.py\n@@ -1,2 +1,2 @@\n"
            "-def f():\n-    return 1\n+def f():\n+    return 2\n"
        )
        stripped = rb.oracle_structural(reference_patch, candidate_patch)
        unstripped = rb.oracle_structural(reference_patch, candidate_patch, test_patterns=())

        self.assertEqual(stripped["files_jaccard"], 1.0)
        self.assertEqual(unstripped["files_jaccard"], 0.5)
        self.assertGreater(stripped["files_jaccard"], unstripped["files_jaccard"])
        self.assertGreater(stripped["hunk_overlap"], unstripped["hunk_overlap"])
        for result in (stripped, unstripped):
            self.assertEqual(result["label"], rb.STRUCTURAL_LABEL)


class SizeProfileStripTests(unittest.TestCase):
    """P1-F5 + Nit applies the SAME strip to `size_profile` sizing -- a candidate must never
    be priced for LOC it structurally cannot produce (the withheld test blob)."""

    def test_size_profile_is_sized_off_the_stripped_patch_not_the_full_diff(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_issue_fixture_repo(repo)
            tasks, _notes = rb.mine_issue_tasks(repo, gh_runner=None)
            task = next(t for t in tasks if t["issue"] == 7)

            # `reference_patch` itself is untouched -- T2's mining boundary, not this task's.
            self.assertIn("tests/test_m.py", task["reference_patch"])

            stripped_loc = rb._changed_loc(rb._strip_test_hunks(task["reference_patch"]))
            self.assertEqual(task["size_profile"], rb._size_profile(stripped_loc))

    def test_a_large_test_hunk_would_have_inflated_the_size_label_unstripped(self):
        # Synthetic reference patch whose test hunk alone crosses the XS->S threshold --
        # proves the strip changes the PRICED OUTCOME, not just the raw LOC count.
        source_hunk = (
            "--- a/m.py\n+++ b/m.py\n@@ -1,2 +1,2 @@\n-def f():\n-    return 1\n"
            "+def f():\n+    return 2\n"
        )
        big_test_hunk_body = "\n".join(f"+assert m.f() == {i}" for i in range(20))
        test_hunk = (
            "--- a/tests/test_m.py\n+++ b/tests/test_m.py\n"
            f"@@ -0,0 +1,20 @@\n{big_test_hunk_body}\n"
        )
        reference_patch = source_hunk + test_hunk

        full_loc = rb._changed_loc(reference_patch)
        stripped_loc = rb._changed_loc(rb._strip_test_hunks(reference_patch))
        self.assertGreater(full_loc, stripped_loc)
        self.assertNotEqual(rb._size_profile(full_loc), rb._size_profile(stripped_loc))
        self.assertEqual(rb._size_profile(stripped_loc), "XS")


def build_oracle_fixture_repo(root):
    """A one-commit target the grade substrate can be CONSTRUCTED from. Returns HEAD.

    T12R/F1 changed oracle (a) from "copy the candidate's tree and clean it" to "construct the
    substrate from the base tree, the in-scope patch and the blobs", so these unit tests need a
    real base tree to construct FROM — a bare scratch directory is no longer a substrate the
    oracle will accept, and that refusal is the point rather than an inconvenience.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    (root / "m.py").write_text("def f():\n    return 1\n")
    (root / "run_tests.py").write_text('HARNESS = "stock"\n')
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "c1: buggy f() and its harness")
    return _git(root, "rev-parse", "HEAD").strip()


def _oracle_task(base_commit, *, mode="issue-replay", blobs=None, scope_path="m.py"):
    """A minimal task record shaped for `oracle_tests` — `scope_path` is what the reference
    patch touches, i.e. the whitelist."""
    return {
        "task_id": "t1",
        "mode": mode,
        "oracle_tests_available": True,
        "test_blobs": dict(blobs or {}),
        "base_commit": base_commit,
        "setup_patch": None,
        "reference_patch": (
            f"--- a/{scope_path}\n+++ b/{scope_path}\n@@ -1,2 +1,2 @@\n-old\n+new\n"
        ),
    }


def _candidate_patch_for(target_repo, base_commit, mutate, dest):
    """A REAL captured candidate patch: build a sandbox off `base_commit`, let `mutate` write
    in it, and capture. Never hand-rolled — the whole question is what the engine does with
    the diff its own capture path produces."""
    info = rb.make_sandbox(target_repo, base_commit, dest)
    mutate(Path(info["path"]))
    return rb.capture_patch(info["path"]), Path(info["path"])


class OracleTestsTests(unittest.TestCase):
    """Oracle (a) -- `solved` can ONLY ever come from `oracle_tests` (PLAN D5)."""

    def test_unavailable_without_a_test_cmd_passed_stays_none(self):
        task = _oracle_task("0" * 40)
        with tempfile.TemporaryDirectory() as td:
            result = rb.oracle_tests(task, "", None, None, Path(td) / "scratch")
        self.assertEqual(result["oracle"], "tests")
        self.assertFalse(result["available"])
        self.assertIsNone(result["passed"])

    def test_unavailable_issue_replay_without_blobs_passed_stays_none_never_false(self):
        task = _oracle_task("0" * 40)
        task["oracle_tests_available"] = False
        with tempfile.TemporaryDirectory() as td:
            result = rb.oracle_tests(task, "", "irrelevant-cmd", None, Path(td) / "scratch")
        self.assertFalse(result["available"])
        self.assertIsNone(result["passed"])

    def test_without_a_target_repo_the_oracle_refuses_rather_than_grading_the_candidate(self):
        """T12R/F1: there is deliberately NO fallback to grading the candidate's own tree.
        Without a base tree the substrate cannot be constructed, so the oracle reports itself
        unavailable — never a silent `passed: True`, and never a cleaned-up candidate tree."""
        task = _oracle_task("0" * 40)
        calls = []
        with tempfile.TemporaryDirectory() as td:
            result = rb.oracle_tests(
                task, "", "cmd", lambda cmd, cwd: calls.append(cwd) or (0, "OK"),
                Path(td) / "scratch",
            )
        self.assertFalse(result["available"])
        self.assertIsNone(result["passed"])
        self.assertIsNone(result["out_of_scope"])
        self.assertIn(rb.SUBSTRATE_UNAVAILABLE_NOTE, result["notes"])
        self.assertEqual(calls, [], "the test command ran without a constructed substrate")

    def test_blob_lands_in_the_substrate_and_never_in_the_candidate_sandbox(self):
        seen = {}

        def runner(cmd, cwd):
            seen["cwd"] = str(cwd)
            seen["blob_present"] = (Path(cwd) / "tests" / "test_m.py").exists()
            return 0, "OK"

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            base = build_oracle_fixture_repo(repo)
            task = _oracle_task(
                base, blobs={"tests/test_m.py": "import m\nassert m.f() == 2\n"}
            )
            patch, sandbox = _candidate_patch_for(
                repo, base, lambda cwd: (cwd / "m.py").write_text("def f():\n    return 2\n"),
                td / "cand",
            )
            result = rb.oracle_tests(
                task, patch, "cmd", runner, td / "scratch", target_repo=repo
            )
            self.assertTrue(seen["blob_present"], "the withheld blob never reached the substrate")
            self.assertNotEqual(seen["cwd"], str(sandbox))
            self.assertFalse(
                (sandbox / "tests" / "test_m.py").exists(),
                "fix-test blob leaked into the candidate's own sandbox",
            )
        self.assertTrue(result["available"])
        self.assertTrue(result["passed"])
        self.assertEqual(result["rc"], 0)

    def test_pass_and_fail_both_directions_from_the_same_blob_test(self):
        def make_runner(rc):
            def runner(cmd, cwd):
                return rc, "output"
            return runner

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            base = build_oracle_fixture_repo(repo)
            task = _oracle_task(
                base, blobs={"tests/test_m.py": "import m\nassert m.f() == 2\n"}
            )
            patch, _sandbox = _candidate_patch_for(
                repo, base, lambda cwd: (cwd / "m.py").write_text("def f():\n    return 2\n"),
                td / "cand",
            )
            passing = rb.oracle_tests(
                task, patch, "cmd", make_runner(0), td / "scratch", target_repo=repo
            )
            failing = rb.oracle_tests(
                task, patch, "cmd", make_runner(1), td / "scratch", target_repo=repo
            )
        self.assertTrue(passing["passed"])
        self.assertEqual(passing["rc"], 0)
        self.assertFalse(failing["passed"])
        self.assertEqual(failing["rc"], 1)

    def test_general_mode_grades_without_any_blobs_the_repos_own_tests_are_already_there(self):
        calls = []

        def runner(cmd, cwd):
            calls.append(cwd)
            return 0, "OK"

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            base = build_oracle_fixture_repo(repo)
            task = _oracle_task(base, mode="general")
            result = rb.oracle_tests(task, "", "cmd", runner, td / "scratch", target_repo=repo)
        self.assertTrue(result["available"])
        self.assertTrue(result["passed"])
        self.assertTrue(calls)

    def test_no_grading_artifacts_survive_under_scratch_dir(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            base = build_oracle_fixture_repo(repo)
            task = _oracle_task(base, mode="general")
            patch, _sandbox = _candidate_patch_for(
                repo, base, lambda cwd: (cwd / "m.py").write_text("def f():\n    return 2\n"),
                td / "cand",
            )
            scratch = td / "scratch"
            result = rb.oracle_tests(
                task, patch, "cmd", lambda cmd, cwd: (0, "OK"), scratch, target_repo=repo
            )
            self.assertTrue(result["available"], result["notes"])
            leftovers = list(scratch.rglob("*")) if scratch.exists() else []
        self.assertEqual(leftovers, [], f"the substrate left artifacts behind: {leftovers}")


class OracleTestsRedCheckTests(unittest.TestCase):
    """PLAN D5/T6 item 2 -- a task green at base is not a discriminating oracle (R6)."""

    def test_not_applicable_without_a_test_cmd(self):
        task = {
            "mode": "issue-replay", "oracle_tests_available": True, "base_commit": "x",
            "test_blobs": {},
        }
        with tempfile.TemporaryDirectory() as td:
            result = rb.oracle_tests_red_check(task, Path(td), None, None, Path(td) / "scratch")
        self.assertIsNone(result)

    def test_not_applicable_for_general_mode_it_was_red_validated_at_mining(self):
        task = {
            "mode": "general", "oracle_tests_available": True, "base_commit": "x",
            "test_blobs": {},
        }
        with tempfile.TemporaryDirectory() as td:
            result = rb.oracle_tests_red_check(task, Path(td), "cmd", None, Path(td) / "scratch")
        self.assertIsNone(result)

    def test_not_applicable_without_test_blobs(self):
        task = {
            "mode": "issue-replay", "oracle_tests_available": False, "base_commit": "x",
            "test_blobs": {},
        }
        with tempfile.TemporaryDirectory() as td:
            result = rb.oracle_tests_red_check(task, Path(td), "cmd", None, Path(td) / "scratch")
        self.assertIsNone(result)

    def test_demotion_signal_when_the_base_already_passes(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            tasks, _notes = rb.mine_issue_tasks(repo, gh_runner=None)
            task = next(t for t in tasks if t["issue"] == 7)
            self.assertTrue(task["oracle_tests_available"])

            result = rb.oracle_tests_red_check(
                task, repo, "cmd", lambda cmd, cwd: (0, "OK"), td / "scratch",
            )
        self.assertEqual(result, {"checked": True, "passed_at_base": True})

    def test_a_genuinely_red_base_is_not_demoted(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            tasks, _notes = rb.mine_issue_tasks(repo, gh_runner=None)
            task = next(t for t in tasks if t["issue"] == 7)

            result = rb.oracle_tests_red_check(
                task, repo, "cmd", lambda cmd, cwd: (1, "FAIL"), td / "scratch",
            )
        self.assertEqual(result, {"checked": True, "passed_at_base": False})

    def test_no_base_sandbox_survives_under_scratch_dir(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            tasks, _notes = rb.mine_issue_tasks(repo, gh_runner=None)
            task = next(t for t in tasks if t["issue"] == 7)
            scratch = td / "scratch"
            rb.oracle_tests_red_check(task, repo, "cmd", lambda c, w: (1, "x"), scratch)
            leftovers = list(scratch.rglob("*")) if scratch.exists() else []
        self.assertEqual(leftovers, [], f"red-check sandbox left artifacts behind: {leftovers}")


def _f_returns_2_test_runner(cmd, cwd):
    """A STUB `test_runner` standing in for the fixture's real assertion (`m.f() == 2`):
    deterministic on the actual content of `m.py` in whatever directory it is handed, so a
    genuinely-fixed candidate reads GREEN and a genuinely-buggy base reads RED -- no real
    subprocess, no interpretation of `cmd`."""
    content = (Path(cwd) / "m.py").read_text()
    return (0, "OK") if "return 2" in content else (1, "FAIL: f() does not return 2")


def _fixing_dispatch_runner(argv, cwd):
    """A stub DISPATCH runner that actually fixes `m.py` (unlike `make_stub_runner`, which
    only ever adds an unrelated file) -- needed to prove the tests oracle can read GREEN."""
    (Path(cwd) / "m.py").write_text("def f():\n    return 2\n")
    return 0, _canned_result_json()


class RunLoopOraclesTests(unittest.TestCase):
    """T6 item 4 -- both oracles wired into `cmd_run`'s per-cell flow, after patch capture."""

    def _run(self, td, dispatch_runner, test_runner, extra=()):
        td = Path(td)
        repo = td / "target"
        build_issue_fixture_repo(repo)
        store = td / "store"
        # `--mode issue-replay` forced: with `--test-cmd` given, `auto` would otherwise
        # count the fixture's 2 mined pairs against `MIN_EVIDENCE_TASKS` (5) and fall back
        # to general (mutation-repair) mode -- these tests are specifically about the
        # issue-replay blob/red-check machinery.
        args = _run_args(
            repo, store, "--live", "--max-usd", "1000000", "--test-cmd", "run-tests",
            "--mode", "issue-replay", *extra,
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rb.cmd_run(args, runner=dispatch_runner, test_runner=test_runner)
        results = json.loads(
            (Path(rb.list_runs(store)[0][0]["path"]) / "results.json").read_text()
        )
        return results

    def test_every_cell_carries_both_oracles(self):
        with tempfile.TemporaryDirectory() as td:
            results = self._run(
                td, _fixing_dispatch_runner, _f_returns_2_test_runner,
            )
            for cell in results["cells"]:
                self.assertIn("oracles", cell)
                # T20 narrowed this from an exact set to a superset: the cell now also carries
                # the full-patch DIAGNOSTIC under its own key. The two graded oracles are still
                # asserted present, and `test_the_diagnostic_lives_beside_solved_and_never_in_it`
                # below pins that the new key is separate from — and unreadable by — `solved`.
                self.assertLessEqual({"tests", "structural"}, set(cell["oracles"]))
                self.assertIn("full_patch", cell["oracles"])
                self.assertEqual(cell["oracles"]["structural"]["label"], rb.STRUCTURAL_LABEL)
                self.assertEqual(
                    cell["oracles"]["full_patch"]["label"], rb.FULL_PATCH_DIAGNOSTIC_LABEL
                )

    def test_a_genuine_fix_reads_green_and_a_task_without_blobs_stays_unavailable(self):
        with tempfile.TemporaryDirectory() as td:
            results = self._run(td, _fixing_dispatch_runner, _f_returns_2_test_runner)
            by_task = {}
            for cell in results["cells"]:
                by_task.setdefault(cell["task_id"], cell)

            fix_cell = next(c for tid, c in by_task.items() if tid.startswith("issue-7-"))
            notest_cell = next(c for tid, c in by_task.items() if tid.startswith("issue-9-"))

            self.assertTrue(fix_cell["oracles"]["tests"]["available"])
            self.assertTrue(fix_cell["oracles"]["tests"]["passed"])
            self.assertEqual(fix_cell["oracles"]["tests"]["rc"], 0)

            self.assertFalse(notest_cell["oracles"]["tests"]["available"])
            self.assertIsNone(notest_cell["oracles"]["tests"]["passed"])

    def test_red_check_demotes_a_non_discriminating_task_across_every_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            results = self._run(
                td, make_stub_runner(), lambda cmd, cwd: (0, "OK"), extra=("--models", "haiku,sonnet"),
            )
            fix_cells = [c for c in results["cells"] if c["task_id"].startswith("issue-7-")]
            self.assertTrue(fix_cells)
            for cell in fix_cells:
                self.assertFalse(cell["oracles"]["tests"]["available"])
                self.assertIsNone(cell["oracles"]["tests"]["passed"])
                self.assertEqual(
                    cell["oracles"]["tests"]["notes"], rb.TESTS_NOT_DISCRIMINATING_NOTE,
                )

    def test_blobs_never_reach_the_candidates_own_sandbox_even_with_a_test_cmd(self):
        with tempfile.TemporaryDirectory() as td:
            results = self._run(
                td, make_stub_runner(), _f_returns_2_test_runner, extra=("--keep-work",),
            )
            run_dir = Path(rb.list_runs(Path(td) / "store")[0][0]["path"])
            task_blobs = {
                json.loads(p.read_text())["task_id"]: json.loads(p.read_text())["test_blobs"]
                for p in (run_dir / "tasks").glob("*.json")
            }
            for cell_dir in (run_dir / "work").iterdir():
                if not cell_dir.is_dir() or not cell_dir.name.startswith("cell-"):
                    continue
                for blobs in task_blobs.values():
                    for rel_path in blobs:
                        self.assertFalse(
                            (cell_dir / rel_path).exists(),
                            f"fix-test blob {rel_path} leaked into candidate sandbox {cell_dir}",
                        )
            # …and grading left no trace of its own copies/red-check sandboxes either.
            stray = [
                p.name for p in (run_dir / "work").iterdir()
                if p.is_dir() and not p.name.startswith("cell-")
            ]
            self.assertEqual(stray, [], f"grading scratch survived under work/: {stray}")

    def test_no_test_cmd_leaves_every_tests_oracle_unavailable(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            store = td / "store"
            args = _run_args(repo, store, "--live", "--max-usd", "1000000")
            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_run(args, runner=make_stub_runner())
            results = json.loads(
                (Path(rb.list_runs(store)[0][0]["path"]) / "results.json").read_text()
            )
            for cell in results["cells"]:
                self.assertFalse(cell["oracles"]["tests"]["available"])
                self.assertIsNone(cell["oracles"]["tests"]["passed"])


# ---------------------------------------------------------------------------------------------
# T7 — Oracle (c): the blind LLM judge (PLAN D6).


class BuildJudgePromptTests(unittest.TestCase):
    TASK = {"statement": "fix the bug", "task_id": "t1", "subject": "s"}

    def test_slot_seed_zero_and_one_disagree_and_cover_both_letters(self):
        p0, s0 = rb.build_judge_prompt(self.TASK, "REFPATCH", "CANDPATCH", 0)
        p1, s1 = rb.build_judge_prompt(self.TASK, "REFPATCH", "CANDPATCH", 1)
        self.assertNotEqual(s0, s1)
        self.assertEqual({"A", "B"}, set(s0))
        self.assertEqual({"A", "B"}, set(s1))
        self.assertEqual({"reference", "candidate"}, set(s0.values()))
        self.assertEqual({"reference", "candidate"}, set(s1.values()))
        self.assertTrue(p0)
        self.assertTrue(p1)

    def test_prompt_contains_both_patches_verbatim(self):
        prompt, _slots = rb.build_judge_prompt(
            self.TASK, "UNIQUE-REF-TEXT-1", "UNIQUE-CAND-TEXT-2", 0
        )
        self.assertIn("UNIQUE-REF-TEXT-1", prompt)
        self.assertIn("UNIQUE-CAND-TEXT-2", prompt)

    def test_prompt_never_names_which_slot_is_which(self):
        for seed in (0, 1):
            prompt, _slots = rb.build_judge_prompt(self.TASK, "REFPATCH", "CANDPATCH", seed)
            self.assertNotIn("reference", prompt.lower())
            self.assertNotIn("candidate", prompt.lower())

    def test_prompt_asks_for_the_strict_grammar(self):
        prompt, _slots = rb.build_judge_prompt(self.TASK, "REFPATCH", "CANDPATCH", 0)
        self.assertIn(
            "GRADE A=<correct|partial|incorrect> B=<correct|partial|incorrect> "
            "EQUIVALENT=<yes|no>",
            prompt,
        )

    def test_statement_falls_back_to_subject(self):
        task = {"task_id": "t2", "subject": "the commit subject"}
        prompt, _slots = rb.build_judge_prompt(task, "R", "C", 0)
        self.assertIn("the commit subject", prompt)


class ParseJudgeOutputTests(unittest.TestCase):
    def test_candidate_grade_follows_the_slot_not_the_letter(self):
        # SAME raw grammar line, two different slot maps -- the semantic candidate/reference
        # grades must flip with the slot, proving the blind-slot design actually works.
        output = "some rationale\nGRADE A=correct B=incorrect EQUIVALENT=no\nmore rationale"
        a_is_candidate = {"A": "candidate", "B": "reference"}
        b_is_candidate = {"A": "reference", "B": "candidate"}

        g1 = rb.parse_judge_output(output, a_is_candidate)
        g2 = rb.parse_judge_output(output, b_is_candidate)

        self.assertEqual(g1["candidate_grade"], "correct")
        self.assertEqual(g1["reference_grade"], "incorrect")
        self.assertEqual(g2["candidate_grade"], "incorrect")
        self.assertEqual(g2["reference_grade"], "correct")
        self.assertNotEqual(g1["candidate_grade"], g2["candidate_grade"])

    def test_unparseable_output_returns_none(self):
        slots = {"A": "candidate", "B": "reference"}
        self.assertIsNone(rb.parse_judge_output("no grammar here at all", slots))
        self.assertIsNone(rb.parse_judge_output("", slots))
        self.assertIsNone(rb.parse_judge_output(None, slots))
        self.assertIsNone(rb.parse_judge_output("GRADE A=maybe B=correct EQUIVALENT=no", slots))

    def test_equivalent_yes_no_maps_to_a_bool(self):
        slots = {"A": "candidate", "B": "reference"}
        yes = rb.parse_judge_output("GRADE A=correct B=correct EQUIVALENT=yes", slots)
        no = rb.parse_judge_output("GRADE A=correct B=partial EQUIVALENT=no", slots)
        self.assertIs(yes["equivalent"], True)
        self.assertIs(no["equivalent"], False)

    def test_slots_are_echoed_back_verbatim(self):
        slots = {"A": "reference", "B": "candidate"}
        g = rb.parse_judge_output("GRADE A=correct B=partial EQUIVALENT=no", slots)
        self.assertEqual(g["slots"], slots)

    def test_grammar_line_is_found_amid_surrounding_rationale(self):
        slots = {"A": "candidate", "B": "reference"}
        output = (
            "Looking at both patches...\n"
            "GRADE A=partial B=correct EQUIVALENT=no\n"
            "Patch B handles the edge case, Patch A does not.\n"
        )
        g = rb.parse_judge_output(output, slots)
        self.assertIsNotNone(g)
        self.assertEqual(g["candidate_grade"], "partial")
        self.assertEqual(g["reference_grade"], "correct")


class OracleJudgeTests(unittest.TestCase):
    TASK = {"statement": "fix the thing", "task_id": "t1", "subject": "s"}

    def test_judge_equal_to_candidate_model_raises_before_any_dispatch(self):
        calls = []

        def runner(argv, cwd):
            calls.append(argv)
            return 0, "GRADE A=correct B=correct EQUIVALENT=yes"

        with self.assertRaises(ValueError):
            rb.oracle_judge(
                self.TASK, "REF", "CAND", "fake-haiku-1", rb.CLAUDE_ADAPTER, runner,
                "stub-bin", FIXTURE_PRICING, slot_seed=0, candidate_model="fake-haiku-1",
            )
        self.assertEqual(calls, [], "the belt-and-braces check must refuse BEFORE dispatch")

    def test_a_different_candidate_model_does_not_raise(self):
        runner = make_stub_runner(output="GRADE A=correct B=correct EQUIVALENT=yes")
        grade = rb.oracle_judge(
            self.TASK, "REF", "CAND", "fake-opus-1", rb.CLAUDE_ADAPTER, runner, "stub-bin",
            FIXTURE_PRICING, slot_seed=0, candidate_model="fake-haiku-1",
        )
        self.assertEqual(grade["judge_model"], "fake-opus-1")

    def test_no_candidate_model_supplied_skips_the_belt_and_braces_check(self):
        runner = make_stub_runner(output="GRADE A=correct B=correct EQUIVALENT=yes")
        grade = rb.oracle_judge(
            self.TASK, "REF", "CAND", "fake-haiku-1", rb.CLAUDE_ADAPTER, runner, "stub-bin",
            FIXTURE_PRICING, slot_seed=0,
        )
        self.assertEqual(grade["judge_model"], "fake-haiku-1")

    def test_slot_seed_controls_the_argv_the_runner_sees(self):
        # A properly diff-shaped reference patch -- `oracle_judge` strips test-pattern file
        # blocks before prompting (P1-F5 + Nit below), and a bare non-diff string has no file
        # blocks to begin with, so it would strip to nothing and prove nothing here.
        reference_patch = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-UNIQUE-REF-XYZ\n+UNIQUE-REF-XYZ\n"
        seen_argvs = []

        def runner(argv, cwd):
            seen_argvs.append(argv)
            return 0, "GRADE A=correct B=partial EQUIVALENT=no"

        grade = rb.oracle_judge(
            self.TASK, reference_patch, "UNIQUE-CAND-XYZ", "fake-opus-1", rb.CLAUDE_ADAPTER,
            runner, "stub-bin", FIXTURE_PRICING, slot_seed=0,
        )
        self.assertEqual(grade["slots"], {"A": "candidate", "B": "reference"})
        prompt = seen_argvs[-1][-1]
        self.assertIn("UNIQUE-REF-XYZ", prompt)
        self.assertIn("UNIQUE-CAND-XYZ", prompt)
        self.assertEqual(seen_argvs[-1][0], "stub-bin")
        self.assertTrue(rb.argv_carries_output_format(seen_argvs[-1]))

    def test_parse_failure_records_none_grade_and_the_unparseable_note(self):
        runner = make_stub_runner(output="total gibberish, no grammar anywhere in here")
        grade = rb.oracle_judge(
            self.TASK, "REF", "CAND", "fake-opus-1", rb.CLAUDE_ADAPTER, runner, "stub-bin",
            FIXTURE_PRICING, slot_seed=0,
        )
        self.assertIsNone(grade["grade"])
        self.assertEqual(grade["notes"], rb.JUDGE_UNPARSEABLE_NOTE)
        self.assertEqual(grade["label"], rb.JUDGE_LABEL)
        self.assertEqual(grade["oracle"], "judge")
        self.assertIn("A", grade["slots"])

    def test_parseable_output_never_carries_the_unparseable_note(self):
        runner = make_stub_runner(output="GRADE A=correct B=correct EQUIVALENT=yes")
        grade = rb.oracle_judge(
            self.TASK, "REF", "CAND", "fake-opus-1", rb.CLAUDE_ADAPTER, runner, "stub-bin",
            FIXTURE_PRICING, slot_seed=0,
        )
        self.assertIsNotNone(grade["grade"])
        self.assertEqual(grade["notes"], "")

    def test_actual_usage_prices_the_actual_basis(self):
        # `make_stub_runner`'s canned JSON has no GRADE line -> the grade is unparseable, but
        # usage IS extractable, so the dollar basis must still read `actual`.
        runner = make_stub_runner(usage=STUB_USAGE, output=None)
        grade = rb.oracle_judge(
            self.TASK, "REF", "CAND", "fake-opus-1", rb.CLAUDE_ADAPTER, runner, "stub-bin",
            FIXTURE_PRICING, slot_seed=0,
        )
        self.assertIsNone(grade["grade"])
        self.assertEqual(grade["usd_basis"], "actual")
        self.assertAlmostEqual(
            grade["usd"], rb.price_usage("fake-opus-1", STUB_USAGE, FIXTURE_PRICING)
        )

    def test_garbage_output_degrades_usd_to_the_judge_grade_profile_estimate(self):
        runner = make_stub_runner(output="not json at all, no usage, no grammar")
        grade = rb.oracle_judge(
            self.TASK, "REF", "CAND", "fake-opus-1", rb.CLAUDE_ADAPTER, runner, "stub-bin",
            FIXTURE_PRICING, slot_seed=0,
        )
        self.assertEqual(grade["usd_basis"], "estimated")
        self.assertAlmostEqual(
            grade["usd"],
            rb.estimate_dispatch_usd("fake-opus-1", rb.JUDGE_GRADE_PROFILE, FIXTURE_PRICING),
        )

    def test_reference_patch_is_stripped_of_test_hunks_before_the_prompt(self):
        # P1-F5 + Nit, carried into T7: the reference's own withheld test hunk must never
        # reach the judge's prompt -- it is a structural tell (one patch adds tests, the
        # other never does) that defeats the blind slot design.
        reference_patch = (
            "--- a/m.py\n+++ b/m.py\n@@ -1,2 +1,2 @@\n"
            "-def f():\n-    return 1\n+def f():\n+    return 2\n"
            "--- a/tests/test_m.py\n+++ b/tests/test_m.py\n@@ -0,0 +1,2 @@\n"
            "+import m\n+assert m.f() == 2\n"
        )
        seen_argvs = []

        def runner(argv, cwd):
            seen_argvs.append(argv)
            return 0, "GRADE A=correct B=correct EQUIVALENT=yes"

        rb.oracle_judge(
            self.TASK, reference_patch, "candidate patch text, source only", "fake-opus-1",
            rb.CLAUDE_ADAPTER, runner, "stub-bin", FIXTURE_PRICING, slot_seed=0,
        )
        prompt = seen_argvs[-1][-1]
        self.assertNotIn("assert m.f() == 2", prompt)
        self.assertNotIn("import m", prompt)
        self.assertIn("def f():", prompt)

    def test_there_is_no_caller_supplied_directory_seam_for_the_judges_cwd(self):
        """F1 (Phase 3 review). T7 gave `oracle_judge` a `scratch_dir` seam and `cmd_run`
        pointed it at `<run-dir>/work`, which put `../../tasks/<id>.json` (reference patch +
        withheld test blobs) and `../../dispatches/<id>__<model>.json` (the candidate's model
        id) two `cat`s from a dispatch running with permissions bypassed. The seam is gone —
        the `prepare_cell_sandbox` precedent: an optional "put it here" is a leak waiting for
        the next caller to re-open."""
        self.assertNotIn(
            "scratch_dir", inspect.signature(rb.oracle_judge).parameters,
            "oracle_judge grew back a caller-supplied cwd seam",
        )
        self.assertNotIn("scratch_dir", inspect.signature(rb.grade_cells).parameters)

    def test_the_judge_cwd_is_a_fresh_empty_throwaway_directory(self):
        seen = []

        def runner(argv, cwd):
            seen.append((Path(cwd), sorted(p.name for p in Path(cwd).iterdir())))
            return 0, "GRADE A=correct B=correct EQUIVALENT=yes"

        rb.oracle_judge(
            self.TASK, "REF", "CAND", "fake-opus-1", rb.CLAUDE_ADAPTER, runner, "stub-bin",
            FIXTURE_PRICING, slot_seed=0,
        )
        cwd, contents = seen[0]
        self.assertEqual(contents, [], f"the judge's cwd was not empty: {contents}")
        self.assertFalse(cwd.exists(), "the judge's throwaway cwd outlived the dispatch")

    def test_general_mode_grades_carry_the_weaker_blinding_note(self):
        """F6 (Phase 3 review): in general mode the reference is the exact inverse of ONE
        mutation operator — one file, ±1 line — beside real agent output. `JUDGE_LABEL` says
        "bias-controlled" unqualified, so the residual tell has to be said out loud."""
        runner = make_stub_runner(output="GRADE A=correct B=correct EQUIVALENT=yes")
        general = rb.oracle_judge(
            {**self.TASK, "mode": "general"}, "REF", "CAND", "fake-opus-1", rb.CLAUDE_ADAPTER,
            runner, "stub-bin", FIXTURE_PRICING, slot_seed=0,
        )
        issue = rb.oracle_judge(
            {**self.TASK, "mode": "issue-replay"}, "REF", "CAND", "fake-opus-1",
            rb.CLAUDE_ADAPTER, runner, "stub-bin", FIXTURE_PRICING, slot_seed=0,
        )
        self.assertIn(rb.JUDGE_GENERAL_BLINDING_NOTE, general["notes"])
        self.assertNotIn(rb.JUDGE_GENERAL_BLINDING_NOTE, issue["notes"])
        self.assertEqual(general["label"], rb.JUDGE_LABEL)

    def test_an_unparseable_general_mode_grade_carries_both_notes(self):
        runner = make_stub_runner(output="no grammar here at all")
        grade = rb.oracle_judge(
            {**self.TASK, "mode": "general"}, "REF", "CAND", "fake-opus-1", rb.CLAUDE_ADAPTER,
            runner, "stub-bin", FIXTURE_PRICING, slot_seed=0,
        )
        self.assertIn(rb.JUDGE_UNPARSEABLE_NOTE, grade["notes"])
        self.assertIn(rb.JUDGE_GENERAL_BLINDING_NOTE, grade["notes"])

    def test_no_scratch_dir_falls_back_to_a_usable_system_temp_cwd(self):
        seen_cwds = []

        def runner(argv, cwd):
            seen_cwds.append(cwd)
            self.assertTrue(Path(cwd).is_dir())
            return 0, "GRADE A=correct B=correct EQUIVALENT=yes"

        rb.oracle_judge(
            self.TASK, "REF", "CAND", "fake-opus-1", rb.CLAUDE_ADAPTER, runner, "stub-bin",
            FIXTURE_PRICING, slot_seed=0,
        )
        self.assertTrue(seen_cwds)


class GradeCellsTests(unittest.TestCase):
    #: T7R/F4c: these reference patches are diff-SHAPED on purpose. A bare `"REF1"` parses to
    #: no file blocks at all, so it strips to nothing — and a task whose stripped reference is
    #: empty now buys no judge grade (an empty `Patch A` deanonymises the pair and grades
    #: nothing). Every dispatch these tests are about needs a reference the judge could
    #: actually read.
    TASKS = [
        {
            "task_id": "t1", "mode": "issue-replay", "statement": "s1", "subject": "s1",
            "reference_patch": "--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-REF1 before\n+REF1 after\n",
        },
        {
            "task_id": "t2", "mode": "issue-replay", "statement": "s2", "subject": "s2",
            "reference_patch": "--- a/b.py\n+++ b/b.py\n@@ -1 +1 @@\n-REF2 before\n+REF2 after\n",
        },
    ]

    def test_spend_state_threads_through_a_happy_path(self):
        cells = [{"task_id": "t1", "model": "fake-haiku-1", "patch": "P1", "skipped": None}]
        runner = make_stub_runner(usage=STUB_USAGE, output=None)
        grades, spent_usd, stopped = rb.grade_cells(
            cells, self.TASKS, "fake-opus-1", rb.CLAUDE_ADAPTER, runner, "stub-bin",
            FIXTURE_PRICING, 0.0, 1000.0,
        )
        self.assertFalse(stopped)
        self.assertEqual(len(grades), 1)
        self.assertIsNone(grades[0]["skipped"])
        self.assertAlmostEqual(spent_usd, grades[0]["usd"])
        self.assertEqual(grades[0]["usd_basis"], "actual")
        self.assertEqual(grades[0]["task_id"], "t1")
        self.assertEqual(grades[0]["candidate_model"], "fake-haiku-1")

    def test_starting_spend_carries_forward(self):
        cells = [{"task_id": "t1", "model": "fake-haiku-1", "patch": "P1", "skipped": None}]
        runner = make_stub_runner(usage=STUB_USAGE, output=None)
        grades, spent_usd, stopped = rb.grade_cells(
            cells, self.TASKS, "fake-opus-1", rb.CLAUDE_ADAPTER, runner, "stub-bin",
            FIXTURE_PRICING, 5.0, 1000.0,
        )
        self.assertFalse(stopped)
        self.assertAlmostEqual(spent_usd, 5.0 + grades[0]["usd"])

    def test_a_cell_already_skipped_for_cost_ceiling_gets_a_matching_skipped_grade_with_no_dispatch(self):
        cells = [{"task_id": "t1", "model": "fake-haiku-1", "patch": None, "skipped": "cost-ceiling"}]
        calls = []

        def runner(argv, cwd):
            calls.append(argv)
            return 0, "GRADE A=correct B=correct EQUIVALENT=yes"

        grades, spent_usd, stopped = rb.grade_cells(
            cells, self.TASKS, "fake-opus-1", rb.CLAUDE_ADAPTER, runner, "stub-bin",
            FIXTURE_PRICING, 0.0, 1000.0,
        )
        self.assertEqual(calls, [], "an already-skipped cell must never reach the runner")
        self.assertEqual(len(grades), 1)
        self.assertEqual(grades[0]["skipped"], "cost-ceiling")
        self.assertIsNone(grades[0]["grade"])
        self.assertIsNone(grades[0]["usd"])
        self.assertFalse(stopped, "a pre-skipped cell alone must not flip the grading stop flag")
        self.assertAlmostEqual(spent_usd, 0.0)

    def test_a_ceiling_that_covers_one_grade_but_not_two_stops_cleanly(self):
        cells = [
            {"task_id": "t1", "model": "fake-haiku-1", "patch": "P1", "skipped": None},
            {"task_id": "t2", "model": "fake-haiku-1", "patch": "P2", "skipped": None},
        ]
        judge_unit = rb.estimate_dispatch_usd("fake-opus-1", rb.JUDGE_GRADE_PROFILE, FIXTURE_PRICING)
        # Garbage output -> no extractable usage -> each dispatched grade's `usd` is exactly
        # the estimate, so the ceiling math below is exact, not merely directional.
        runner = make_stub_runner(output="GRADE A=correct B=partial EQUIVALENT=no")
        max_usd = judge_unit * 1.5  # room for exactly one grade, not two

        grades, spent_usd, stopped = rb.grade_cells(
            cells, self.TASKS, "fake-opus-1", rb.CLAUDE_ADAPTER, runner, "stub-bin",
            FIXTURE_PRICING, 0.0, max_usd, slot_seed=0,
        )

        self.assertTrue(stopped)
        self.assertEqual(len(grades), 2)
        self.assertIsNone(grades[0]["skipped"])
        self.assertIsNotNone(grades[0]["grade"])
        self.assertEqual(grades[1]["skipped"], "cost-ceiling")
        self.assertIsNone(grades[1]["grade"])
        self.assertIsNone(grades[1]["usd"])
        self.assertAlmostEqual(spent_usd, judge_unit)
        self.assertEqual(len(runner.calls), 1, "the second grade must never reach the runner")

    def test_judge_equal_to_a_cells_own_candidate_model_raises(self):
        cells = [{"task_id": "t1", "model": "fake-opus-1", "patch": "P1", "skipped": None}]
        runner = make_stub_runner(output="GRADE A=correct B=correct EQUIVALENT=yes")
        with self.assertRaises(ValueError):
            rb.grade_cells(
                cells, self.TASKS, "fake-opus-1", rb.CLAUDE_ADAPTER, runner, "stub-bin",
                FIXTURE_PRICING, 0.0, 1000.0,
            )


class SpendBasisWithGradesTests(unittest.TestCase):
    """P2-F5: `_spend_basis` must see grade records too, not just cells."""

    def test_actual_cells_but_estimated_grades_is_mixed(self):
        cells = [{"usd_basis": "actual", "skipped": None}]
        grades = [{"usd_basis": "estimated", "skipped": None}]
        self.assertEqual(rb._spend_basis(cells, grades), "mixed")

    def test_all_estimated_stays_estimated(self):
        cells = [{"usd_basis": "estimated", "skipped": None}]
        grades = [{"usd_basis": "estimated", "skipped": None}]
        self.assertEqual(rb._spend_basis(cells, grades), "estimated")

    def test_skipped_grades_are_excluded_from_the_basis_set(self):
        cells = [{"usd_basis": "actual", "skipped": None}]
        grades = [{"usd_basis": None, "skipped": "cost-ceiling"}]
        self.assertEqual(rb._spend_basis(cells, grades), "actual")

    def test_omitting_grades_keeps_the_pre_t7_behaviour(self):
        cells = [{"usd_basis": "actual", "skipped": None}]
        self.assertEqual(rb._spend_basis(cells), "actual")

    def test_all_actual_across_both_stays_actual(self):
        cells = [{"usd_basis": "actual", "skipped": None}]
        grades = [{"usd_basis": "actual", "skipped": None}]
        self.assertEqual(rb._spend_basis(cells, grades), "actual")


# ---------------------------------------------------------------------------------------------
# T7R — Phase 3 remediation. Still offline and free: fixture repos in temp dirs, injected
# dispatch runners, and — where a STUB test runner would hide the defect on purpose (a forged
# test only forges anything if something actually reads the test file) — a local
# `sys.executable` command running stdlib-only code inside a copy we built.


def _py_test_cmd(body):
    """A REAL test command: `python -c <body>`, run only inside a sandbox/grade copy this suite
    built. `-c` puts the cwd on `sys.path`, so the code under grading imports normally."""
    return f"{shlex.quote(sys.executable)} -c " + shlex.quote(body)


#: Reads the repo's OWN test file and executes it — so a candidate that rewrites that file
#: changes the verdict. That is the whole point: `make_stub_runner`-style stubs cannot express
#: the forgery F2 is about.
GENERAL_FORGERY_TEST_CMD = _py_test_cmd("exec(open('tests/test_calc.py').read())")

ISSUE_FORGERY_TEST_CMD = _py_test_cmd(
    "import sys; sys.path.insert(0, 'tests'); exec(open('tests/test_m.py').read())"
)


def build_forgeable_issue_fixture_repo(root):
    """An issue-replay fixture with a SHARED test helper the fix commit never touches.

    That helper is the forgery surface F2 is about: the withheld `test_blobs` (here
    `tests/test_m.py`) are restored into the grade copy, but they call into `tests/helper.py`,
    which the fix did not touch — so a candidate that guts the helper and never fixes `m.py`
    made the restored test pass anyway. Returns the fix sha.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    (root / "m.py").write_text("def f():\n    return 1\n")
    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "helper.py").write_text(
        "def check(value):\n    assert value == 2, 'f() is still wrong'\n"
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "c1: buggy f(), plus the shared assertion helper")

    (root / "m.py").write_text("def f():\n    return 2\n")
    (tests_dir / "test_m.py").write_text("import m\nfrom helper import check\ncheck(m.f())\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixes #7: f() should return 2")
    return _git(root, "rev-parse", "HEAD").strip()


def _old_style_grade(sandbox, task, test_cmd):
    """The PRE-T7R oracle-(a) algorithm, reproduced: copy the candidate's post-dispatch tree,
    write only the fix commit's `test_blobs` on top, run the command. Used to prove a forgery
    really would have graded GREEN — a test that only asserts the new behaviour cannot show
    that the hole was real."""
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "copy"
        shutil.copytree(str(sandbox), str(copy))
        for rel_path, blob in (task.get("test_blobs") or {}).items():
            target = copy / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(blob)
        return rb.default_test_runner(test_cmd, str(copy))[0]


class ForgeableSolvedTests(unittest.TestCase):
    """F2 (Phase 3 review) — `solved` is the ONE signal D5 lets mean correctness, and it was
    forgeable: oracle (a) graded a COPY OF THE CANDIDATE'S OWN TREE with only the fix commit's
    test blobs restored (in general mode: nothing at all). A candidate that ignored the bug and
    rewrote the test passed. Every number downstream — the tier map, the daily-driver pick, a
    routing change a user might apply — rests on that bit."""

    def test_general_mode_test_rewrite_cannot_earn_solved(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            head, _ = build_parity_fixture_repo(repo)
            store = td / "store"

            def forging_runner(argv, cwd):
                cwd = Path(cwd)
                if not (cwd / "calc.py").exists():  # the judge's throwaway cwd
                    return 0, _canned_result_json()
                # The bug in calc.py is left exactly where it is; the TEST is neutered.
                (cwd / "tests" / "test_calc.py").write_text("assert True\n")
                return 0, _canned_result_json()

            args = rb.build_parser().parse_args([
                "run", "--repo", str(repo), "--models", "haiku", "--mode", "general",
                "--test-cmd", GENERAL_FORGERY_TEST_CMD, "--store-dir", str(store),
                "--live", "--max-usd", "1000000", "--keep-work",
            ])
            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_run(args, runner=forging_runner)

            run_dir = Path(rb.list_runs(store)[0][0]["path"])
            results = json.loads((run_dir / "results.json").read_text())
            cells = [c for c in results["cells"] if not c["skipped"]]
            self.assertTrue(cells, results["notes"])
            for cell in cells:
                tests = cell["oracles"]["tests"]
                self.assertTrue(tests["available"], tests)
                self.assertFalse(
                    tests["passed"],
                    "a candidate that rewrote the test instead of fixing the bug was SOLVED",
                )
                self.assertEqual(cell["candidate_touched_tests"], ["tests/test_calc.py"])

            # …and the same tree really would have graded GREEN under the old algorithm.
            tasks = [json.loads(p.read_text()) for p in (run_dir / "tasks").glob("*.json")]
            by_id = {t["task_id"]: t for t in tasks}
            sandbox = next(
                p for p in (run_dir / "work").iterdir()
                if p.is_dir() and p.name.startswith("cell-")
            )
            self.assertEqual(
                _old_style_grade(sandbox, by_id[cells[0]["task_id"]], GENERAL_FORGERY_TEST_CMD),
                0,
                "the forgery no longer forges anything — this test proves nothing",
            )

    def test_issue_replay_gutting_an_untouched_helper_cannot_earn_solved(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_forgeable_issue_fixture_repo(repo)
            store = td / "store"

            def forging_runner(argv, cwd):
                cwd = Path(cwd)
                if not (cwd / "m.py").exists():  # the judge's throwaway cwd
                    return 0, _canned_result_json()
                # m.py keeps its bug; the helper the FIX never touched is gutted instead.
                (cwd / "tests" / "helper.py").write_text("def check(value):\n    return True\n")
                return 0, _canned_result_json()

            args = rb.build_parser().parse_args([
                "run", "--repo", str(repo), "--models", "haiku", "--mode", "issue-replay",
                "--test-cmd", ISSUE_FORGERY_TEST_CMD, "--store-dir", str(store),
                "--live", "--max-usd", "1000000", "--keep-work",
            ])
            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_run(args, runner=forging_runner)

            run_dir = Path(rb.list_runs(store)[0][0]["path"])
            results = json.loads((run_dir / "results.json").read_text())
            cells = [c for c in results["cells"] if not c["skipped"]]
            self.assertTrue(cells, results["notes"])
            cell = cells[0]
            self.assertTrue(cell["oracles"]["tests"]["available"], cell["oracles"]["tests"])
            self.assertFalse(
                cell["oracles"]["tests"]["passed"],
                "gutting a test file the fix never touched still earned `solved`",
            )
            self.assertEqual(cell["candidate_touched_tests"], ["tests/helper.py"])
            self.assertTrue(
                any(rb.CANDIDATE_TOUCHED_TESTS_NOTE in n for n in results["notes"]),
                results["notes"],
            )

            tasks = {
                json.loads(p.read_text())["task_id"]: json.loads(p.read_text())
                for p in (run_dir / "tasks").glob("*.json")
            }
            sandbox = next(
                p for p in (run_dir / "work").iterdir()
                if p.is_dir() and p.name.startswith("cell-")
            )
            self.assertEqual(
                _old_style_grade(sandbox, tasks[cell["task_id"]], ISSUE_FORGERY_TEST_CMD), 0,
                "the forgery no longer forges anything — this test proves nothing",
            )

    def test_a_genuine_fix_still_reads_solved_through_the_restored_test_surface(self):
        """The other half of F2: restoring the base test surface must not make solving
        IMPOSSIBLE. Same fixture, same real test command — a candidate that actually fixes
        `m.py` and touches no test still grades green, and carries no test-edit flag."""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_forgeable_issue_fixture_repo(repo)
            store = td / "store"

            def fixing_runner(argv, cwd):
                cwd = Path(cwd)
                if not (cwd / "m.py").exists():
                    return 0, _canned_result_json()
                (cwd / "m.py").write_text("def f():\n    return 2\n")
                return 0, _canned_result_json()

            args = rb.build_parser().parse_args([
                "run", "--repo", str(repo), "--models", "haiku", "--mode", "issue-replay",
                "--test-cmd", ISSUE_FORGERY_TEST_CMD, "--store-dir", str(store),
                "--live", "--max-usd", "1000000",
            ])
            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_run(args, runner=fixing_runner)

            results = json.loads(
                (Path(rb.list_runs(store)[0][0]["path"]) / "results.json").read_text()
            )
            cell = next(c for c in results["cells"] if not c["skipped"])
            self.assertTrue(cell["oracles"]["tests"]["available"])
            self.assertTrue(cell["oracles"]["tests"]["passed"], cell["oracles"]["tests"])
            self.assertEqual(cell["candidate_touched_tests"], [])

    def test_a_candidate_created_test_file_never_reaches_the_substrate(self):
        """The other forgery shape: not editing an existing test but ADDING one (a
        `conftest`-alike, a trivially-green module the runner would pick up).

        T7R deleted it from a copy of the candidate's tree. T12R never puts it there: the
        substrate is CONSTRUCTED from the base tree plus the candidate's in-scope hunks, and a
        file the reference patch never touched is not in scope, so it is simply not applied.
        The candidate's own sandbox is untouched because this function never reads it at all.
        """
        seen = {}

        def runner(cmd, cwd):
            seen["planted"] = (Path(cwd) / "tests" / "test_planted.py").exists()
            return 0, "OK"

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            base = build_oracle_fixture_repo(repo)
            task = _oracle_task(base, mode="general")
            patch, sandbox = _candidate_patch_for(
                repo, base,
                lambda cwd: (
                    (cwd / "tests").mkdir(exist_ok=True),
                    (cwd / "tests" / "test_planted.py").write_text("assert True\n"),
                ),
                td / "cand",
            )
            result = rb.oracle_tests(
                task, patch, "cmd", runner, td / "scratch", target_repo=repo
            )
            self.assertTrue(
                (sandbox / "tests" / "test_planted.py").exists(),
                "grading mutated the candidate's own sandbox",
            )
        self.assertFalse(seen["planted"], "a candidate-planted test file reached grading")
        self.assertEqual(result["out_of_scope"], ["tests/test_planted.py"])


class GradingFailureEnvelopeTests(unittest.TestCase):
    """F3 (Phase 3 review) — the `finally` exists so a mid-run failure still leaves a labelled
    envelope. T7 reintroduced the exact defect it was created to fix by adding a SPENDING step
    (judge grading) above the write: a raising judge dispatch destroyed `results.json` after
    real candidate money had been spent."""

    def test_a_raising_judge_dispatch_still_leaves_a_labelled_envelope(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            store = td / "store"

            card = rb.build_plan(repo, ["haiku"], scratch_dir=td / "plan-scratch")
            judge_id = card["judge"]

            def runner(argv, cwd):
                model = argv[argv.index("--model") + 1]
                if model == judge_id:
                    raise RuntimeError("the judge binary vanished mid-grade")
                (Path(cwd) / "candidate_fix.py").write_text("# real, paid-for work\n")
                return 0, _canned_result_json()

            args = _run_args(repo, store, "--live", "--max-usd", "1000000")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = rb.cmd_run(args, runner=runner)

            self.assertEqual(rc, 0, "a grading failure is a labelled outcome, not a crash")
            run_dir = Path(rb.list_runs(store)[0][0]["path"])
            results_path = run_dir / "results.json"
            self.assertTrue(
                results_path.exists(),
                "a raising judge dispatch destroyed the envelope after real spend",
            )
            results = json.loads(results_path.read_text())
            self.assertIn(rb.GRADING_FAILED_LABEL, results["labels"])
            self.assertTrue(any(rb.GRADING_FAILED_NOTE in n for n in results["notes"]))
            self.assertGreater(results["spend"]["spent_usd"], 0.0, "candidate spend was lost")
            self.assertIn(rb.SPEND_BASIS_LABELS[results["spend"]["basis"]], results["labels"])
            self.assertNotIn(rb.ABORTED_LABEL, results["labels"])
            # the store's siblings are written after grading — and still got written
            self.assertTrue(list((run_dir / "tasks").glob("*.json")))
            self.assertTrue(list((run_dir / "dispatches").glob("*.json")))
            self.assertIn("results.json:", out.getvalue())

    def test_an_aborted_run_carries_an_empty_grades_list(self):
        """T7-informational, carried into T7R: an aborted run must not spend on grading. The
        property was only asserted INDIRECTLY before (via the envelope test); this asserts it
        where it is visible — `grades: []`, and not one judge argv on the runner."""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            store = td / "store"

            card = rb.build_plan(repo, ["haiku"], scratch_dir=td / "plan-scratch")
            seen_models = []

            def exploding_runner(argv, cwd):
                seen_models.append(argv[argv.index("--model") + 1])
                if len(seen_models) >= 2:
                    raise RuntimeError("the harness died mid-run")
                (Path(cwd) / "candidate_fix.py").write_text("# work\n")
                return 0, _canned_result_json()

            args = _run_args(repo, store, "--live", "--max-usd", "1000000")
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
                rb.cmd_run(args, runner=exploding_runner)

            results = json.loads(
                (Path(rb.list_runs(store)[0][0]["path"]) / "results.json").read_text()
            )
            self.assertEqual(results["grades"], [], "an aborted run paid for judge grades")
            self.assertNotIn(card["judge"], seen_models)
            self.assertIn(rb.ABORTED_LABEL, results["labels"])


class ColorProofReferenceDiffTests(unittest.TestCase):
    """F4a (Phase 3 review) — the candidate diff pins `--no-color --no-ext-diff`; the reference
    diff did not, and inherited the TARGET's own `color.ui = always`. ANSI escapes make every
    `+++`/`---` header unparseable: the reference strips to nothing, `size_profile` collapses
    to XS for every task in that repo, and the judge's `Patch A` renders EMPTY."""

    def test_a_target_with_color_ui_always_still_yields_a_parseable_reference(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "target"
            build_issue_fixture_repo(repo)
            _git(repo, "config", "color.ui", "always")
            _git(repo, "config", "diff.colorMoved", "zebra")

            tasks, _notes = rb.mine_issue_tasks(repo, gh_runner=None)
            task = next(t for t in tasks if t["issue"] == 7)

            self.assertNotIn("\x1b[", task["reference_patch"], "the reference diff is coloured")
            paths = [p for p, _text in rb._split_diff_by_file(task["reference_patch"])]
            self.assertIn("m.py", paths)
            self.assertIn("tests/test_m.py", paths)
            self.assertTrue(
                rb._strip_test_hunks(task["reference_patch"]).strip(),
                "the stripped reference came out empty — F4's collapse, again",
            )
            self.assertEqual(sorted(task["test_blobs"]), ["tests/test_m.py"])


class StructuralAvailabilityTests(unittest.TestCase):
    """F4b + nits (Phase 3 review) — oracle (b) is "always available" in the sense that it needs
    no test command, NOT in the sense that it always has numbers. An empty stripped reference
    renders `n/a`, never `0.0`."""

    REF = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a = 1\n+a = 2\n"
    CAND = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a = 1\n+a = 2\n"

    def test_an_empty_reference_is_unavailable_with_no_numbers(self):
        result = rb.oracle_structural("", self.CAND)
        self.assertFalse(result["available"])
        self.assertIsNone(result["files_jaccard"])
        self.assertIsNone(result["hunk_overlap"])
        self.assertIsNone(result["loc_delta_ratio"])
        self.assertIsNone(result["out_of_scope_files"])
        self.assertEqual(result["notes"], rb.STRUCTURAL_NO_REFERENCE_NOTE)
        self.assertEqual(result["label"], rb.STRUCTURAL_LABEL)

    def test_a_tests_only_reference_strips_to_nothing_and_is_unavailable(self):
        tests_only = (
            "--- a/tests/test_flaky.py\n+++ b/tests/test_flaky.py\n@@ -1 +1 @@\n"
            "-assert flaky()\n+assert stable()\n"
        )
        result = rb.oracle_structural(tests_only, self.CAND)
        self.assertFalse(result["available"], "a tests-only fix left a made-up 0.0 behind")
        self.assertIsNone(result["files_jaccard"])

    def test_unparseable_input_yields_no_agreement_at_all(self):
        result = rb.oracle_structural("garbage", "garbage")
        self.assertFalse(result["available"])
        self.assertIn(result.get("loc_delta_ratio"), (None, 0.0))

    def test_a_real_comparison_is_still_available_and_numeric(self):
        result = rb.oracle_structural(self.REF, self.CAND)
        self.assertTrue(result["available"])
        self.assertEqual(result["files_jaccard"], 1.0)
        self.assertEqual(result["notes"], "")

    def test_a_whitespace_only_candidate_patch_gets_the_no_change_note(self):
        result = rb.oracle_structural(self.REF, "   \n\t\n")
        self.assertTrue(result["available"])
        self.assertEqual(result["notes"], "candidate produced no change")
        self.assertEqual(result["files_jaccard"], 0.0)


class EmptyReferenceBuysNoJudgeGradeTests(unittest.TestCase):
    """F4c (Phase 3 review) — an empty stripped reference renders one slot EMPTY: the pair
    deanonymises itself, the grade means nothing, and it parses cleanly enough to be recorded
    as real. Paying for that is the worst of both."""

    TASKS = [{
        "task_id": "tests-only", "mode": "issue-replay", "statement": "s", "subject": "s",
        "reference_patch": (
            "--- a/tests/test_flaky.py\n+++ b/tests/test_flaky.py\n@@ -1 +1 @@\n"
            "-assert flaky()\n+assert stable()\n"
        ),
    }]

    def test_no_dispatch_and_a_stated_reason(self):
        cells = [{
            "task_id": "tests-only", "model": "fake-haiku-1", "patch": "P", "skipped": None,
        }]
        runner = make_stub_runner(output="GRADE A=correct B=correct EQUIVALENT=yes")
        grades, spent_usd, stopped = rb.grade_cells(
            cells, self.TASKS, "fake-opus-1", rb.CLAUDE_ADAPTER, runner, "stub-bin",
            FIXTURE_PRICING, 0.0, 1000.0,
        )
        self.assertEqual(runner.calls, [], "a meaningless grade was dispatched and paid for")
        self.assertEqual(grades[0]["skipped"], rb.SKIPPED_EMPTY_REFERENCE)
        self.assertEqual(grades[0]["notes"], rb.JUDGE_EMPTY_REFERENCE_NOTE)
        self.assertIsNone(grades[0]["grade"])
        self.assertIsNone(grades[0]["usd"])
        self.assertAlmostEqual(spent_usd, 0.0)
        self.assertFalse(stopped, "an empty reference is not a ceiling stop")

    def test_it_is_not_counted_as_a_cost_ceiling_casualty(self):
        cells = [{
            "task_id": "tests-only", "model": "fake-haiku-1", "patch": "P", "skipped": None,
        }]
        grades, _spent, _stopped = rb.grade_cells(
            cells, self.TASKS, "fake-opus-1", rb.CLAUDE_ADAPTER, make_stub_runner(), "stub-bin",
            FIXTURE_PRICING, 0.0, 1000.0,
        )
        self.assertNotEqual(grades[0]["skipped"], rb.SKIPPED_COST_CEILING)


class RedCheckRunsFirstTests(unittest.TestCase):
    """Nit (Phase 3 review) — oracle (a) used to run BEFORE the red check, so the target's
    arbitrary test command executed once per cell even for tasks the red check then demoted:
    PLAN D11 exposure bought for a grade nobody may read."""

    def test_a_demoted_task_never_runs_the_test_command_for_grading(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            store = td / "store"
            cwds = []

            def counting_test_runner(cmd, cwd):
                cwds.append(str(cwd))
                return 0, "OK"  # green at base -> the task is demoted

            args = _run_args(
                repo, store, "--live", "--max-usd", "1000000", "--test-cmd", "run-tests",
                "--mode", "issue-replay", "--models", "haiku,sonnet",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_run(args, runner=make_stub_runner(), test_runner=counting_test_runner)

            self.assertEqual(
                len(cwds), 1,
                f"the demoted task's test command ran {len(cwds)} times; once (the red check "
                f"at base) is the whole budget: {cwds}",
            )
            results = json.loads(
                (Path(rb.list_runs(store)[0][0]["path"]) / "results.json").read_text()
            )
            for cell in results["cells"]:
                if cell["task_id"].startswith("issue-7-"):
                    self.assertEqual(
                        cell["oracles"]["tests"]["notes"], rb.TESTS_NOT_DISCRIMINATING_NOTE
                    )
                    self.assertIsNone(
                        cell["oracles"]["tests"]["rc"],
                        "a demoted record kept an rc from a run whose result nobody may read",
                    )


# ---------------------------------------------------------------------------------------------
# T8 — `verdict`: the explicit combination rule, the evidence floor, the three legs.
#
# THE POINT OF THIS BLOCK: this is where all four oracles finally meet, and the last place the
# discipline every layer above was built for can be lost. Every test below is a guard against
# one specific way a number could start claiming more than it measured: `solved` widening past
# oracle (a), an `n/a` rendering as 0.00, a below-floor verdict reading as routing-grade, a leg
# quietly dropped, or a composite score appearing anywhere.
#
# Every fixture here is synthetic and lives in a temp store (GUARDRAILS sanctions fixture
# envelopes in TEMP stores for reader tests; the real store is never touched), and every model
# id in them is obviously fake.


#: Fixture pricing -- obviously-fake ids only (GUARDRAILS: no real model id in a fixture).
#: Used for the tier join the OBSERVED leg performs; no price is read from it anywhere.
FAKE_PRICING = {
    "models": {
        "fake-alpha-1": {"tier": "haiku"},
        "fake-beta-1": {"tier": "sonnet"},
        "fake-gamma-1": {"tier": "opus"},
        "fake-delta-1": {"tier": "frontier"},
    }
}

_CANDIDATE_PATCH = (
    "diff --git a/src/m.py b/src/m.py\n--- a/src/m.py\n+++ b/src/m.py\n"
    "@@ -1 +1 @@\n-old\n+new\n"
)


def _v_cell(task_id, model, *, tests_available=True, passed=True, structural_available=True,
            files=0.5, hunks=0.5, loc=0.5, out_of_scope=0, usd=0.01, usd_basis="actual",
            wall=1.0, touched=(), skipped=None, tests_rc=None, tests_notes="",
            estimated_usd=0.02):
    """One synthetic results.json cell. `skipped` goes through the module's OWN
    `_skipped_cell`, so the `oracles: None` sentinel these tests must survive is the real
    one, not a hand-written imitation of it. `estimated_usd` (T18) is overridable so
    calibration tests can pin a known actual/estimate ratio; every pre-T18 caller keeps the
    old 0.02 default unchanged."""
    if skipped:
        return rb._skipped_cell(task_id, model, 0.02, reason=skipped)
    return {
        "task_id": task_id,
        "model": model,
        "wall_seconds": wall,
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "usd": usd,
        "usd_basis": usd_basis,
        "patch": _CANDIDATE_PATCH,
        "dispatch_rc": 0,
        "estimated_usd": estimated_usd,
        "skipped": None,
        "oracles": {
            "tests": {
                "oracle": "tests",
                "available": tests_available,
                "passed": (bool(passed) if tests_available else None),
                "rc": tests_rc,
                "notes": tests_notes,
            },
            "structural": {
                "oracle": "structural",
                "available": structural_available,
                "files_jaccard": files if structural_available else None,
                "hunk_overlap": hunks if structural_available else None,
                "loc_delta_ratio": loc if structural_available else None,
                "out_of_scope_files": out_of_scope if structural_available else None,
                "label": rb.STRUCTURAL_LABEL,
                "notes": "",
            },
        },
        "candidate_touched_tests": list(touched),
    }


def _v_grade(task_id, model, grade, *, skipped=None, note=None):
    """One synthetic judge grade. Skips go through the module's own `_skipped_grade`."""
    if skipped:
        return rb._skipped_grade(task_id, model, 0.005, reason=skipped, note=note)
    return {
        "oracle": "judge",
        "task_id": task_id,
        "candidate_model": model,
        "judge_model": "fake-delta-1",
        "slots": {"A": "candidate", "B": "reference"},
        "grade": None if grade is None else {
            "candidate_grade": grade,
            "reference_grade": "correct",
            "equivalent": False,
            "slots": {"A": "candidate", "B": "reference"},
        },
        "usd": 0.001,
        "usd_basis": "actual",
        "label": rb.JUDGE_LABEL,
        "notes": "",
        "dispatch_rc": 0,
        "estimated_usd": 0.005,
        "skipped": None,
    }


def _write_run(store, cells, grades=(), *, candidates=None, labels=(), notes=(),
               profiles=None, spend=None, repo="/nonexistent/target"):
    """A synthetic run dir in a TEMP store -> (run_id, run_dir).

    The dir itself is created by the module's own `new_run_dir` (the real layout, the real
    content-free run id); only the envelope inside it is synthetic, which is exactly what
    GUARDRAILS sanctions for a READER test.
    """
    run_id, run_dir = rb.new_run_dir(store)
    if candidates is None:
        seen = []
        for cell in cells:
            if cell["model"] not in seen:
                seen.append(cell["model"])
        candidates = seen
    results = {
        "store_schema_version": rb.STORE_SCHEMA_VERSION,
        "run_id": run_id,
        "repo": repo,
        "base_commit": "0" * 40,
        "mode": "issue-replay",
        "harness": "stub-harness",
        "candidates": list(candidates),
        "judge": "fake-delta-1",
        "cells": list(cells),
        "grades": list(grades),
        "spend": spend or {"ceiling_usd": 10.0, "spent_usd": 0.5, "basis": "actual"},
        "labels": list(labels),
        "notes": list(notes),
    }
    (run_dir / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    if profiles:
        (run_dir / "plan.json").write_text(json.dumps({
            "tasks": [
                {"task_id": tid, "size_profile": prof, "oracle_tests_available": True}
                for tid, prof in profiles.items()
            ],
        }, indent=2) + "\n")
    return run_id, run_dir


def _write_run_with_verdict(store, *, tier_slots, daily_driver_pick, below_floor=False,
                             labels=(), repo="/nonexistent/target", mode="issue-replay",
                             candidates=None, spend=None):
    """T9: a synthetic run dir whose `results.json` already carries a `"verdict"` key --
    exactly the shape `verdict` folds back in (VerdictCliTests.
    test_the_verdict_is_folded_back_into_results_json). `apply_verdict` reads ONLY
    `run_id`/`repo`/`verdict` off the envelope, so cells/grades are deliberately omitted here
    -- this is a fixture for the READER (apply/list), sanctioned in a TEMP store, never the
    real one.
    """
    run_id, run_dir = rb.new_run_dir(store)
    if candidates is None:
        candidates = sorted(
            {v for v in tier_slots.values() if v} | ({daily_driver_pick} if daily_driver_pick else set())
        )
    results = {
        "store_schema_version": rb.STORE_SCHEMA_VERSION,
        "run_id": run_id,
        "repo": repo,
        "base_commit": "0" * 40,
        "mode": mode,
        "harness": "stub-harness",
        "candidates": list(candidates),
        "judge": None,
        "cells": [],
        "grades": [],
        "spend": spend or {"ceiling_usd": 10.0, "spent_usd": 0.5, "basis": "actual"},
        "labels": [],
        "notes": [],
        "verdict": {
            "verdict_schema_version": rb.VERDICT_SCHEMA_VERSION,
            "goal": "both",
            "min_tasks": rb.MIN_EVIDENCE_TASKS,
            "below_floor": below_floor,
            "below_floor_label": rb._below_floor_label(rb.MIN_EVIDENCE_TASKS) if below_floor else None,
            "rule": "synthetic rule text",
            "capability_order": [],
            "tier_map": {
                "slots": dict(tier_slots), "nearest_neighbors": {}, "role_gloss": {}, "notes": [],
            },
            "daily_driver": {"pick": daily_driver_pick, "notes": []},
            "three_legs": [],
            "disagreements": [],
            "labels": list(labels),
            "notes": [],
        },
    }
    (run_dir / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    return run_id, run_dir


def _write_run_with_raw_verdict(store, verdict, *, repo="/nonexistent/target",
                                 mode="issue-replay", candidates=None, spend=None):
    """T9 retry (defect coverage): unlike `_write_run_with_verdict`, `verdict` is written to
    `results.json` EXACTLY as given -- no shape is imposed. This is how a hand-tampered or
    partially-written `results.json` is simulated (GUARDRAILS names this an in-scope threat
    for the apply gate): a `verdict` that omits `below_floor`, sets it to something other
    than a bool, is not a dict at all, or carries a `tier_map`/`daily_driver` in an
    unexpected shape. TEMP store only, per every other fixture in this module."""
    run_id, run_dir = rb.new_run_dir(store)
    results = {
        "store_schema_version": rb.STORE_SCHEMA_VERSION,
        "run_id": run_id,
        "repo": repo,
        "base_commit": "0" * 40,
        "mode": mode,
        "harness": "stub-harness",
        "candidates": list(candidates) if candidates is not None else [],
        "judge": None,
        "cells": [],
        "grades": [],
        "spend": spend or {"ceiling_usd": 10.0, "spent_usd": 0.5, "basis": "actual"},
        "labels": [],
        "notes": [],
        "verdict": verdict,
    }
    (run_dir / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    return run_id, run_dir


def _verdict(run_dir, goal="both", **kw):
    kw.setdefault("pricing", FAKE_PRICING)
    pricing = kw.pop("pricing")
    return rb.build_verdict(run_dir, goal, pricing, **kw)


def _rows_by(card, task_id, candidate):
    return next(
        r for r in card["measurements"]
        if r["task_id"] == task_id and r["candidate"] == candidate
    )


def _summary(card, candidate):
    return next(s for s in card["summaries"] if s["candidate"] == candidate)


def _write_benchmarks(path, pairs):
    """A synthetic published-index fixture: `{model: index}` -> the file `load_benchmarks`
    reads. Fake ids only; the numbers are ranking positions, never prices."""
    path.write_text(json.dumps({
        "index_name": "Synthetic Index",
        "index_version": "v0",
        "cached_date": "2026-01-01",
        "entries": [
            {"model": model, "effort": "max", "provider": "fixture",
             "intelligence_index": index, "usd_per_task": 1.0}
            for model, index in pairs
        ],
    }, indent=2) + "\n")
    return path


def _write_kit_ledger(kits_dir, kit="synthetic-kit", tier_word="haiku", passes=2, retries=1):
    """A tiny synthetic kit whose ledger `routing_scorecard.scan_kits` can read -- the
    OBSERVED leg's input. Never a real kit, never this repo's."""
    kit_dir = Path(kits_dir) / kit
    kit_dir.mkdir(parents=True, exist_ok=True)
    task_lines = ["# TASKS — synthetic", "", "## Phase 1 — synthetic", ""]
    outcome_lines = ["# NOTES — synthetic", "", "## Outcome ledger"]
    n = 0
    for _ in range(passes):
        n += 1
        task_lines += [f"### S{n} — synthetic task", "- status: done", f"- model: {tier_word}", ""]
        outcome_lines.append(
            f"outcome: S{n} model={tier_word} attempts=1 result=pass review=clean"
        )
    for _ in range(retries):
        n += 1
        task_lines += [f"### S{n} — synthetic task", "- status: done", f"- model: {tier_word}", ""]
        outcome_lines.append(
            f"outcome: S{n} model={tier_word} attempts=2 result=retry-pass review=clean"
        )
    (kit_dir / "TASKS.md").write_text("\n".join(task_lines) + "\n")
    (kit_dir / "NOTES.md").write_text("\n".join(outcome_lines) + "\n")
    return kits_dir


class ResolveMinTasksTests(unittest.TestCase):
    """PLAN D7 — the floor can be RAISED per run and never lowered."""

    def test_no_flag_is_the_structural_floor(self):
        self.assertEqual(rb.resolve_min_tasks(None), rb.MIN_EVIDENCE_TASKS)
        self.assertEqual(rb.MIN_EVIDENCE_TASKS, 5)

    def test_a_lower_flag_cannot_lower_the_floor(self):
        for lower in (0, 1, 3, rb.MIN_EVIDENCE_TASKS - 1):
            self.assertEqual(rb.resolve_min_tasks(lower), rb.MIN_EVIDENCE_TASKS)

    def test_a_higher_flag_raises_it(self):
        self.assertEqual(rb.resolve_min_tasks(9), 9)


class SolvedComesOnlyFromTestsTests(unittest.TestCase):
    """R6, the tripwire this whole task is written around: `solved` is oracle (a) and nothing
    else, forever. A judge that says `correct` over a cell whose tests FAILED changes nothing
    about `solved` — it changes only the judge column."""

    def test_a_judge_correct_over_failing_tests_is_not_solved(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            _run_id, run_dir = _write_run(
                store,
                [_v_cell("t1", "fake-alpha-1", tests_available=True, passed=False)],
                [_v_grade("t1", "fake-alpha-1", "correct")],
            )
            card = _verdict(run_dir)
            summary = _summary(card, "fake-alpha-1")
            self.assertEqual(summary["objective_n"], 1)
            self.assertEqual(summary["solved_n"], 0, "a judge grade produced a `solved`")
            self.assertEqual(summary["judge"]["correct"], 1, "the judge column was lost")
            row = _rows_by(card, "t1", "fake-alpha-1")
            self.assertFalse(row["tests"]["solved"])
            self.assertEqual(row["judge"]["grade"], "correct")
            self.assertIn("| not solved |", rb.render_verdict_markdown(card))

    def test_similarity_alone_never_produces_solved(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            _run_id, run_dir = _write_run(
                store,
                [_v_cell("t1", "fake-alpha-1", tests_available=False,
                         files=1.0, hunks=1.0, loc=1.0)],
                [_v_grade("t1", "fake-alpha-1", "correct")],
            )
            summary = _summary(_verdict(run_dir), "fake-alpha-1")
            self.assertEqual(summary["objective_n"], 0)
            self.assertEqual(summary["solved_n"], 0)
            self.assertIsNone(summary["solved_rate"], "0/0 rendered as a rate")

    def test_a_demoted_tests_record_is_never_read_through_rc(self):
        # A demoted record carries `available: False, passed: None` — and its `rc` must never
        # be consulted. A stale `rc: 0` beside them must NOT read as a pass.
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            _run_id, run_dir = _write_run(
                store,
                [_v_cell("t1", "fake-alpha-1", tests_available=False, tests_rc=0,
                         tests_notes=rb.TESTS_NOT_DISCRIMINATING_NOTE)],
            )
            card = _verdict(run_dir)
            self.assertEqual(_summary(card, "fake-alpha-1")["solved_n"], 0)
            self.assertEqual(_summary(card, "fake-alpha-1")["objective_n"], 0)
            self.assertEqual(rb._tests_cell_text(_rows_by(card, "t1", "fake-alpha-1")), rb.NA)


class EvidenceFloorTests(unittest.TestCase):
    """PLAN D7 — below the floor the CARD is stamped, everywhere it renders, and the raw
    measurement table still prints underneath it."""

    def _card(self, td, objective_cells, **kw):
        store = Path(td) / "store"
        cells = [
            _v_cell(f"t{i}", "fake-alpha-1", tests_available=True, passed=True)
            for i in range(objective_cells)
        ]
        _run_id, run_dir = _write_run(store, cells)
        return _verdict(run_dir, **kw), run_dir

    def test_four_objective_tasks_is_below_the_floor(self):
        with tempfile.TemporaryDirectory() as td:
            card, _ = self._card(td, 4)
            self.assertTrue(card["below_floor"])
            self.assertEqual(card["below_floor_label"], rb._below_floor_label(5))
            self.assertIn(rb._below_floor_label(5), card["labels"])
            self.assertIn("BELOW EVIDENCE FLOOR", rb.render_verdict_markdown(card))

    def test_five_objective_tasks_is_clean(self):
        with tempfile.TemporaryDirectory() as td:
            card, _ = self._card(td, 5)
            self.assertFalse(card["below_floor"])
            self.assertIsNone(card["below_floor_label"])
            self.assertNotIn("BELOW EVIDENCE FLOOR", rb.render_verdict_markdown(card))

    def test_min_tasks_three_still_floors_at_five(self):
        with tempfile.TemporaryDirectory() as td:
            card, _ = self._card(td, 4, min_tasks=3)
            self.assertEqual(card["min_tasks"], 5)
            self.assertTrue(card["below_floor"], "--min-tasks 3 lowered a structural floor")
            self.assertIn(rb._below_floor_label(5), card["labels"])

    def test_min_tasks_can_raise_the_floor(self):
        with tempfile.TemporaryDirectory() as td:
            card, _ = self._card(td, 5, min_tasks=8)
            self.assertEqual(card["min_tasks"], 8)
            self.assertTrue(card["below_floor"])
            self.assertIn(rb._below_floor_label(8), card["labels"])

    def test_the_measurement_table_still_renders_below_the_floor(self):
        with tempfile.TemporaryDirectory() as td:
            card, _ = self._card(td, 2)
            text = rb.render_verdict_markdown(card)
            self.assertIn("BELOW EVIDENCE FLOOR", text)
            self.assertIn("## measurement", text)
            self.assertEqual(text.count("| t0 | fake-alpha-1 |"), 1)
            self.assertEqual(text.count("| t1 | fake-alpha-1 |"), 1)

    def test_one_below_floor_candidate_stamps_the_whole_card(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            cells = [_v_cell(f"t{i}", "fake-alpha-1") for i in range(6)]
            cells.append(_v_cell("t0", "fake-beta-1"))
            _run_id, run_dir = _write_run(store, cells)
            card = _verdict(run_dir)
            self.assertEqual(_summary(card, "fake-alpha-1")["objective_n"], 6)
            self.assertEqual(_summary(card, "fake-beta-1")["objective_n"], 1)
            self.assertTrue(card["below_floor"], "the CARD, not just the candidate, is stamped")


class NaRenderingTests(unittest.TestCase):
    """PLAN D5 — an unavailable oracle renders `n/a`. Never 0.00, never a dropped row. The
    four traps in the inherited cell shape all live here."""

    def test_a_skipped_cell_expands_into_four_labelled_nas(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            _run_id, run_dir = _write_run(
                store,
                [_v_cell("t1", "fake-alpha-1", skipped=rb.SKIPPED_COST_CEILING)],
                [_v_grade("t1", "fake-alpha-1", None, skipped=rb.SKIPPED_COST_CEILING)],
            )
            card = _verdict(run_dir)
            row = _rows_by(card, "t1", "fake-alpha-1")
            self.assertEqual(rb._tests_cell_text(row), rb.NA)
            self.assertEqual(rb._similarity_cell_text(row), rb.NA)
            self.assertTrue(rb._judge_cell_text(row).startswith(rb.NA))
            self.assertIsNone(row["cost"]["usd"])
            self.assertIsNone(row["latency"]["wall_seconds"])

            text = rb.render_verdict_markdown(card)
            line = next(l for l in text.splitlines() if l.startswith("| t1 | fake-alpha-1 |"))
            self.assertNotIn("0.00", line, "an unmeasured cell rendered as a zero")
            # tests, similarity, judge, usd, wall — plus touched-tests, which is `None` (not
            # an empty list) on a cell that produced no patch: absence, not a measured zero.
            # T12R/F1 adds the seventh: `out-of-scope (excluded)`, also `None` here, because
            # a cell that was never dispatched never had a substrate built for it. Rendering
            # `-` there instead would claim "measured, nothing out of scope" about a cell
            # nobody measured — the count moved because a new absence became visible, not
            # because an existing one was softened.
            self.assertEqual(line.count(rb.NA), 7, line)
            self.assertIn("| cost-ceiling |", line, "the skip reason itself was dropped")

    def test_an_absent_judge_grade_is_synthesized_as_na_not_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            # cell present, NO grade record anywhere in the sibling list
            _run_id, run_dir = _write_run(store, [_v_cell("t1", "fake-alpha-1")], [])
            card = _verdict(run_dir)
            row = _rows_by(card, "t1", "fake-alpha-1")
            self.assertEqual(row["judge"]["status"], "no grade record")
            self.assertIn(rb.NA, rb._judge_cell_text(row))
            summary = _summary(card, "fake-alpha-1")
            self.assertEqual(summary["judge"]["no_grade_record"], 1)
            self.assertEqual(summary["judge"]["na"], 1)
            self.assertIn("| t1 | fake-alpha-1 |", rb.render_verdict_markdown(card))

    def test_an_unparseable_grade_renders_na_and_is_not_a_budget_casualty(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            _run_id, run_dir = _write_run(
                store, [_v_cell("t1", "fake-alpha-1")], [_v_grade("t1", "fake-alpha-1", None)]
            )
            summary = _summary(_verdict(run_dir), "fake-alpha-1")
            self.assertEqual(summary["judge"]["unparseable"], 1)
            self.assertEqual(summary["judge"]["skipped_cost_ceiling"], 0)

    def test_an_unavailable_structural_oracle_renders_na(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            _run_id, run_dir = _write_run(
                store, [_v_cell("t1", "fake-alpha-1", structural_available=False)]
            )
            card = _verdict(run_dir)
            row = _rows_by(card, "t1", "fake-alpha-1")
            self.assertEqual(rb._similarity_cell_text(row), rb.NA)
            medians = _summary(card, "fake-alpha-1")["structural_medians"]
            self.assertIsNone(medians["files_jaccard"], "an unavailable oracle became a 0.0")
            self.assertEqual(medians["available_n"], 0)
            self.assertIn(
                rb.STRUCTURAL_LABEL, rb.render_verdict_markdown(card),
                "similarity rendered without its not-a-correctness-verdict label",
            )

    def test_a_missing_cost_never_renders_as_zero_dollars(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            _run_id, run_dir = _write_run(
                store, [_v_cell("t1", "fake-alpha-1", skipped=rb.SKIPPED_COST_CEILING)]
            )
            card = _verdict(run_dir)
            summary = _summary(card, "fake-alpha-1")
            self.assertIsNone(summary["cost"]["usd_total"])
            self.assertIsNone(summary["cost"]["usd_median"])
            self.assertIsNone(summary["latency"]["wall_seconds_median"])
            text = rb.render_verdict_markdown(card)
            self.assertIn(f"total ${rb.NA}", text)

    def test_a_dispatched_cell_with_no_priced_dollars_is_excluded_not_summed_as_zero(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            unpriced = _v_cell("t1", "fake-alpha-1", passed=True)
            unpriced["usd"] = None
            unpriced["usd_basis"] = None
            cells = [unpriced, _v_cell("t2", "fake-alpha-1", passed=True, usd=0.25)]
            _run_id, run_dir = _write_run(store, cells)
            card = _verdict(run_dir)
            cost = _summary(card, "fake-alpha-1")["cost"]
            self.assertEqual(cost["usd_total"], 0.25)
            self.assertEqual(cost["usd_unpriced_n"], 1)
            self.assertIn("not counted as $0", rb.render_verdict_markdown(card))


class JudgeSkipVocabularyTests(unittest.TestCase):
    """T7R carry-forward — `empty-reference` is NOT a budget casualty and must never be
    counted alongside `cost-ceiling`."""

    def test_the_two_skip_reasons_are_counted_apart(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            _run_id, run_dir = _write_run(
                store,
                [_v_cell("t1", "fake-alpha-1"), _v_cell("t2", "fake-alpha-1")],
                [
                    _v_grade("t1", "fake-alpha-1", None, skipped=rb.SKIPPED_EMPTY_REFERENCE,
                             note=rb.JUDGE_EMPTY_REFERENCE_NOTE),
                    _v_grade("t2", "fake-alpha-1", None, skipped=rb.SKIPPED_COST_CEILING),
                ],
            )
            card = _verdict(run_dir)
            judge = _summary(card, "fake-alpha-1")["judge"]
            self.assertEqual(judge["skipped_empty_reference"], 1)
            self.assertEqual(judge["skipped_cost_ceiling"], 1)
            self.assertEqual(judge["na"], 2)

    def test_empty_reference_alone_never_claims_the_budget_starved_the_judge(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            _run_id, run_dir = _write_run(
                store,
                [_v_cell("t1", "fake-alpha-1")],
                [_v_grade("t1", "fake-alpha-1", None, skipped=rb.SKIPPED_EMPTY_REFERENCE)],
            )
            self.assertNotIn(rb.JUDGE_BUDGET_STARVED_LABEL, _verdict(run_dir)["labels"])

    def test_a_wholly_starved_judge_pass_is_named_as_a_budget_outcome(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            _run_id, run_dir = _write_run(
                store,
                [_v_cell("t1", "fake-alpha-1"), _v_cell("t2", "fake-alpha-1")],
                [
                    _v_grade("t1", "fake-alpha-1", None, skipped=rb.SKIPPED_COST_CEILING),
                    _v_grade("t2", "fake-alpha-1", None, skipped=rb.SKIPPED_COST_CEILING),
                ],
            )
            card = _verdict(run_dir)
            self.assertIn(rb.JUDGE_BUDGET_STARVED_LABEL, card["labels"])
            self.assertIn("post-loop pass", rb.JUDGE_BUDGET_STARVED_LABEL)
            self.assertIn(rb.JUDGE_BUDGET_STARVED_LABEL, rb.render_verdict_markdown(card))

    def test_a_graded_run_carries_no_starvation_label(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            _run_id, run_dir = _write_run(
                store,
                [_v_cell("t1", "fake-alpha-1"), _v_cell("t2", "fake-alpha-1")],
                [
                    _v_grade("t1", "fake-alpha-1", "correct"),
                    _v_grade("t2", "fake-alpha-1", None, skipped=rb.SKIPPED_COST_CEILING),
                ],
            )
            self.assertNotIn(rb.JUDGE_BUDGET_STARVED_LABEL, _verdict(run_dir)["labels"])


class CapabilityOrderTests(unittest.TestCase):
    """THE RULE, step (i) — ordered by oracle (a); the judge may ORDER a tie and says so."""

    def test_the_order_is_the_solved_rate_with_counts_shown(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            cells = [_v_cell(f"t{i}", "fake-alpha-1", passed=True) for i in range(3)]
            cells += [_v_cell(f"t{i}", "fake-beta-1", passed=(i == 0)) for i in range(3)]
            _run_id, run_dir = _write_run(store, cells)
            card = _verdict(run_dir)
            self.assertEqual(
                [row["candidate"] for row in card["capability_order"]],
                ["fake-alpha-1", "fake-beta-1"],
            )
            text = "\n".join(card["rule"])
            self.assertIn("solved 3/3", text)
            self.assertIn("solved 1/3", text)

    def test_a_tie_is_broken_by_the_judge_and_annotated_as_subjective(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            cells = [_v_cell("t1", "fake-alpha-1", passed=True),
                     _v_cell("t1", "fake-beta-1", passed=True)]
            grades = [_v_grade("t1", "fake-alpha-1", "partial"),
                      _v_grade("t1", "fake-beta-1", "correct")]
            _run_id, run_dir = _write_run(store, cells, grades)
            card = _verdict(run_dir)
            order = card["capability_order"]
            self.assertEqual(order[0]["candidate"], "fake-beta-1")
            self.assertIn("tiebreak: judge (subjective)", order[0]["tiebreaks"])
            self.assertIn("tiebreak: judge (subjective)", "\n".join(card["rule"]))
            # …and the tie-break never moved the capability numbers themselves
            self.assertEqual(order[0]["solved_n"], order[1]["solved_n"])

    def test_a_candidate_with_no_objective_cell_sorts_last_as_an_absence(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            cells = [_v_cell("t1", "fake-alpha-1", tests_available=False),
                     _v_cell("t1", "fake-beta-1", tests_available=True, passed=False)]
            _run_id, run_dir = _write_run(store, cells)
            card = _verdict(run_dir)
            self.assertEqual(
                [row["candidate"] for row in card["capability_order"]],
                ["fake-beta-1", "fake-alpha-1"],
                "0-of-0 outranked a measured 0-of-1 — absence was read as a score",
            )
            self.assertIsNone(card["capability_order"][1]["solved_rate"])

    def test_the_same_rate_off_different_samples_is_annotated_not_silent(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            # alpha 1/2, beta 2/4 — identical rate, different evidence
            cells = [_v_cell("t0", "fake-alpha-1", passed=True),
                     _v_cell("t1", "fake-alpha-1", passed=False)]
            cells += [_v_cell(f"t{i}", "fake-beta-1", passed=(i < 2)) for i in range(4)]
            _run_id, run_dir = _write_run(store, cells)
            card = _verdict(run_dir)
            order = card["capability_order"]
            self.assertEqual(order[0]["candidate"], "fake-beta-1")
            self.assertIn("tiebreak: larger solved count (still oracle (a))",
                          order[0]["tiebreaks"])
            self.assertEqual(order[0]["solved_rate"], order[1]["solved_rate"])

    def test_the_id_tiebreak_is_ascending_and_annotated(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            cells = [_v_cell("t1", "fake-beta-1", passed=True),
                     _v_cell("t1", "fake-alpha-1", passed=True)]
            _run_id, run_dir = _write_run(store, cells)
            order = _verdict(run_dir)["capability_order"]
            self.assertEqual([r["candidate"] for r in order],
                             ["fake-alpha-1", "fake-beta-1"])
            self.assertIn("tiebreak: candidate id (deterministic, not a signal)",
                          order[0]["tiebreaks"])


class TierMapTests(unittest.TestCase):
    """THE RULE, step (ii) — strong/mid/weak, with the role gloss, and honest about both
    over- and under-supply of candidates."""

    def _card(self, td, candidates):
        store = Path(td) / "store"
        cells = []
        for n, cand in enumerate(candidates):
            for i in range(2):
                cells.append(_v_cell(f"t{i}", cand, passed=(i < 2 - n)))
        _run_id, run_dir = _write_run(store, cells)
        return _verdict(run_dir, goal="tiers")

    def test_three_candidates_fill_the_three_slots_with_the_role_gloss(self):
        with tempfile.TemporaryDirectory() as td:
            card = self._card(td, ["fake-alpha-1", "fake-beta-1", "fake-gamma-1"])
            self.assertEqual(card["tier_map"]["slots"], {
                "strong": "fake-alpha-1", "mid": "fake-beta-1", "weak": "fake-gamma-1",
            })
            self.assertEqual(card["tier_map"]["role_gloss"], rb.TIER_ROLE_GLOSS)
            self.assertIn("strong≈reviewer", rb.render_verdict_markdown(card))

    def test_fewer_candidates_than_tiers_leaves_the_slot_empty_with_a_note(self):
        with tempfile.TemporaryDirectory() as td:
            card = self._card(td, ["fake-alpha-1", "fake-beta-1"])
            self.assertIsNone(card["tier_map"]["slots"]["weak"])
            self.assertTrue(any("unfilled slot" in n for n in card["tier_map"]["notes"]))
            self.assertIn("weak: (empty)", rb.render_verdict_markdown(card))

    def test_more_candidates_than_tiers_lists_the_nearest_neighbours(self):
        with tempfile.TemporaryDirectory() as td:
            card = self._card(
                td, ["fake-alpha-1", "fake-beta-1", "fake-gamma-1", "fake-delta-1"]
            )
            filled = [c for c in card["tier_map"]["slots"].values() if c]
            self.assertEqual(len(filled), 3)
            listed = sum(len(v) for v in card["tier_map"]["nearest_neighbors"].values())
            self.assertEqual(listed, 1, "the fourth candidate was dropped rather than listed")
            self.assertTrue(any("nearest neighbour" in n for n in card["tier_map"]["notes"]))
            self.assertIn("nearest neighbours:", rb.render_verdict_markdown(card))

    def test_the_daily_driver_section_is_absent_for_goal_tiers(self):
        with tempfile.TemporaryDirectory() as td:
            card = self._card(td, ["fake-alpha-1", "fake-beta-1"])
            self.assertIsNone(card["daily_driver"])


class DailyDriverRuleTests(unittest.TestCase):
    """THE RULE, step (iii) — cheap-and-close wins; clearly-worse capability never does."""

    def _build(self, td):
        store = Path(td) / "store"
        profiles = {"q1": "XS", "q2": "S", "q3": "XS", "big1": "L"}
        cells = []
        # alpha: best capability on quick tasks (3/3), most expensive
        for tid in ("q1", "q2", "q3"):
            cells.append(_v_cell(tid, "fake-alpha-1", passed=True, usd=0.10, wall=9.0))
        cells.append(_v_cell("big1", "fake-alpha-1", passed=True, usd=0.10, wall=9.0))
        # beta: within one task of the best (2/3), far cheaper -> the pick
        for tid, ok in (("q1", True), ("q2", True), ("q3", False)):
            cells.append(_v_cell(tid, "fake-beta-1", passed=ok, usd=0.02, wall=3.0))
        cells.append(_v_cell("big1", "fake-beta-1", passed=False, usd=0.02, wall=3.0))
        # gamma: cheapest of all, and clearly worse on capability (0/3)
        for tid in ("q1", "q2", "q3", "big1"):
            cells.append(_v_cell(tid, "fake-gamma-1", passed=False, usd=0.0001, wall=0.5))
        # delta: solves ONLY the big task -> quick-solved 0, so the scoping is what excludes it
        for tid in ("q1", "q2", "q3"):
            cells.append(_v_cell(tid, "fake-delta-1", passed=False, usd=0.0002, wall=0.5))
        cells.append(_v_cell("big1", "fake-delta-1", passed=True, usd=0.0002, wall=0.5))
        _run_id, run_dir = _write_run(store, cells, profiles=profiles)
        return _verdict(run_dir, goal="daily-driver")

    def test_cheap_and_close_wins(self):
        with tempfile.TemporaryDirectory() as td:
            card = self._build(td)
            self.assertEqual(card["daily_driver"]["pick"], "fake-beta-1")

    def test_a_clearly_worse_candidate_is_never_picked_however_cheap(self):
        with tempfile.TemporaryDirectory() as td:
            card = self._build(td)
            rows = {r["candidate"]: r for r in card["daily_driver"]["rows"]}
            self.assertFalse(rows["fake-gamma-1"]["eligible"])
            self.assertFalse(rows["fake-delta-1"]["eligible"])
            self.assertLess(rows["fake-gamma-1"]["usd_median"], rows["fake-beta-1"]["usd_median"])
            self.assertNotEqual(card["daily_driver"]["pick"], "fake-gamma-1")

    def test_the_rule_prints_with_the_numbers_that_decided_it(self):
        with tempfile.TemporaryDirectory() as td:
            card = self._build(td)
            text = "\n".join(card["rule"])
            self.assertIn("within 1 task of the best (3)", text)
            self.assertIn("XS/S", text)
            self.assertIn("quick solved 2/3", text)
            self.assertIn("median usd=0.0200", text)
            self.assertIn("=> pick: fake-beta-1", text)

    def test_the_quick_scope_excludes_larger_tasks(self):
        with tempfile.TemporaryDirectory() as td:
            card = self._build(td)
            rows = {r["candidate"]: r for r in card["daily_driver"]["rows"]}
            self.assertEqual(rows["fake-alpha-1"]["quick_solved_n"], 3)
            self.assertEqual(rows["fake-delta-1"]["quick_solved_n"], 0)

    def test_missing_size_profiles_widen_the_rule_and_say_so(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            cells = [_v_cell("t1", "fake-alpha-1", passed=True, usd=0.5),
                     _v_cell("t1", "fake-beta-1", passed=True, usd=0.1)]
            _run_id, run_dir = _write_run(store, cells)  # no plan.json, no tasks/*.json
            card = _verdict(run_dir, goal="daily-driver")
            self.assertFalse(card["daily_driver"]["profiles_available"])
            self.assertIn(rb.NO_PROFILE_DATA_NOTE, card["daily_driver"]["notes"])
            self.assertEqual(card["daily_driver"]["pick"], "fake-beta-1")

    def test_nobody_solving_anything_is_labelled_a_cost_ordering_not_a_finding(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            cells = [_v_cell("t1", "fake-alpha-1", passed=False, usd=0.5),
                     _v_cell("t1", "fake-beta-1", passed=False, usd=0.1)]
            _run_id, run_dir = _write_run(store, cells, profiles={"t1": "XS"})
            card = _verdict(run_dir, goal="daily-driver")
            self.assertTrue(
                any("not a capability finding" in n for n in card["daily_driver"]["notes"])
            )

    def test_an_unpriced_candidate_is_excluded_rather_than_ranked_at_zero(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            cells = [
                _v_cell("t1", "fake-alpha-1", passed=True, usd=0.5),
                _v_cell("t1", "fake-beta-1", skipped=rb.SKIPPED_COST_CEILING),
            ]
            _run_id, run_dir = _write_run(store, cells, profiles={"t1": "XS"})
            card = _verdict(run_dir, goal="daily-driver")
            self.assertEqual(card["daily_driver"]["pick"], "fake-alpha-1")
            self.assertTrue(
                any("eligible but unpriced" in n for n in card["daily_driver"]["notes"])
            )

    def test_a_task_with_no_recorded_profile_is_excluded_not_assumed_small(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            cells = [_v_cell("q1", "fake-alpha-1", passed=True, usd=0.5),
                     _v_cell("mystery", "fake-alpha-1", passed=True, usd=0.5)]
            _run_id, run_dir = _write_run(store, cells, profiles={"q1": "XS"})
            card = _verdict(run_dir, goal="daily-driver")
            row = card["daily_driver"]["rows"][0]
            self.assertEqual(row["quick_solved_n"], 1, "an unprofiled task was assumed quick")
            self.assertTrue(
                any("no recorded size profile" in n for n in card["daily_driver"]["notes"])
            )


class ThreeLegsTests(unittest.TestCase):
    """PLAN D10 — published prior, observed ledger and this run's measurement stand side by
    side. Never averaged, never merged, and each absence named honestly."""

    def _run(self, td, alpha_pass, beta_pass):
        store = Path(td) / "store"
        cells = [
            _v_cell("t1", "fake-alpha-1", passed=alpha_pass),
            _v_cell("t1", "fake-beta-1", passed=beta_pass),
        ]
        return _write_run(store, cells)

    def test_a_candidate_absent_from_the_index_reads_no_published_entry(self):
        with tempfile.TemporaryDirectory() as td:
            _run_id, run_dir = self._run(td, True, False)
            bench = _write_benchmarks(Path(td) / "bench.json", [("fake-alpha-1", 40)])
            card = _verdict(run_dir, benchmarks_path=bench)
            legs = {leg["candidate"]: leg for leg in card["three_legs"]}
            self.assertEqual(legs["fake-alpha-1"]["published"]["index"], 40)
            self.assertEqual(legs["fake-beta-1"]["published"]["status"], rb.NO_PUBLISHED_ENTRY)
            self.assertIn(rb.NO_PUBLISHED_ENTRY, rb.render_verdict_markdown(card))

    def test_the_id_join_is_bench_routings_normalizer(self):
        with tempfile.TemporaryDirectory() as td:
            _run_id, run_dir = self._run(td, True, False)
            # dotted + upper-cased on the benchmark side; the join must still land
            bench = _write_benchmarks(Path(td) / "bench.json", [("Fake.Alpha.1", 40)])
            card = _verdict(run_dir, benchmarks_path=bench)
            legs = {leg["candidate"]: leg for leg in card["three_legs"]}
            self.assertEqual(legs["fake-alpha-1"]["published"]["index"], 40)

    def test_an_unreadable_benchmarks_file_degrades_with_a_note(self):
        with tempfile.TemporaryDirectory() as td:
            _run_id, run_dir = self._run(td, True, False)
            card = _verdict(run_dir, benchmarks_path=Path(td) / "does-not-exist.json")
            for leg in card["three_legs"]:
                self.assertEqual(leg["published"]["status"], rb.NO_PUBLISHED_ENTRY)
            self.assertTrue(any("published leg unavailable" in n for n in card["notes"]))

    def test_no_kits_dir_means_no_ledger_evidence_not_a_zero_rate(self):
        with tempfile.TemporaryDirectory() as td:
            _run_id, run_dir = self._run(td, True, False)
            card = _verdict(run_dir)
            for leg in card["three_legs"]:
                self.assertEqual(leg["observed"]["status"], rb.NO_LEDGER_EVIDENCE)
                self.assertIsNone(leg["observed"]["rate"])
            self.assertIn(rb.NO_LEDGER_EVIDENCE, rb.render_verdict_markdown(card))

    def test_a_ledger_supplies_the_observed_leg_through_routing_scorecard(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            _run_id, run_dir = self._run(td, True, False)
            kits = _write_kit_ledger(td / "kits", passes=3, retries=1)
            card = _verdict(run_dir, kits_dir=kits)
            legs = {leg["candidate"]: leg for leg in card["three_legs"]}
            alpha = legs["fake-alpha-1"]          # fixture pricing puts it in the haiku tier
            self.assertEqual(alpha["observed"]["tier"], "haiku")
            self.assertEqual(alpha["observed"]["first_try"], 3)
            self.assertEqual(alpha["observed"]["with_outcome"], 4)
            self.assertAlmostEqual(alpha["observed"]["rate"], 0.75)
            # a tier the ledger says nothing about stays honestly empty
            self.assertEqual(legs["fake-beta-1"]["observed"]["status"], rb.NO_LEDGER_EVIDENCE)

    def test_a_thin_ledger_carries_the_insufficient_sample_idiom(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            _run_id, run_dir = self._run(td, True, False)
            kits = _write_kit_ledger(td / "kits", passes=1, retries=0)
            card = _verdict(run_dir, kits_dir=kits)
            legs = {leg["candidate"]: leg for leg in card["three_legs"]}
            self.assertIn("insufficient sample", legs["fake-alpha-1"]["observed"]["status"])
            self.assertTrue(any("LIVE_MIN_SAMPLE" in n for n in card["notes"]))

    def test_disagreement_fires_when_the_published_order_is_inverted(self):
        with tempfile.TemporaryDirectory() as td:
            _run_id, run_dir = self._run(td, True, False)   # measured: alpha > beta
            bench = _write_benchmarks(
                Path(td) / "bench.json", [("fake-alpha-1", 10), ("fake-beta-1", 90)]
            )
            card = _verdict(run_dir, benchmarks_path=bench)
            self.assertEqual(len(card["disagreements"]), 1, card["disagreements"])
            note = card["disagreements"][0]
            self.assertTrue(note.startswith(rb.DISAGREEMENT_PREFIX))
            self.assertIn("published index ranks fake-beta-1 above fake-alpha-1", note)
            self.assertIn("measurement ranks fake-alpha-1 above fake-beta-1", note)
            self.assertIn(note, rb.render_verdict_markdown(card))

    def test_no_disagreement_when_the_legs_agree(self):
        with tempfile.TemporaryDirectory() as td:
            _run_id, run_dir = self._run(td, True, False)
            bench = _write_benchmarks(
                Path(td) / "bench.json", [("fake-alpha-1", 90), ("fake-beta-1", 10)]
            )
            self.assertEqual(_verdict(run_dir, benchmarks_path=bench)["disagreements"], [])

    def test_disagreement_never_fires_on_absent_measurement(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            cells = [_v_cell("t1", "fake-alpha-1", tests_available=False),
                     _v_cell("t1", "fake-beta-1", tests_available=False)]
            _run_id, run_dir = _write_run(store, cells)
            bench = _write_benchmarks(
                Path(td) / "bench.json", [("fake-alpha-1", 10), ("fake-beta-1", 90)]
            )
            self.assertEqual(_verdict(run_dir, benchmarks_path=bench)["disagreements"], [])

    def test_the_three_legs_are_never_merged_into_one_number(self):
        with tempfile.TemporaryDirectory() as td:
            _run_id, run_dir = self._run(td, True, False)
            bench = _write_benchmarks(
                Path(td) / "bench.json", [("fake-alpha-1", 10), ("fake-beta-1", 90)]
            )
            card = _verdict(run_dir, benchmarks_path=bench)
            blob = json.dumps(card).lower()
            for forbidden in ('"score"', '"overall"', '"composite"', '"weighted"', '"blend'):
                self.assertNotIn(forbidden, blob, f"a blended scalar appeared: {forbidden}")
            self.assertIn(rb.THREE_LEGS_LABEL, card["labels"])


class VerdictLabelCarryTests(unittest.TestCase):
    """T7R carry-forward — the ENVELOPE's own honesty labels survive into the verdict. A
    verdict rendered off a partial run must carry that run's partiality."""

    def test_envelope_labels_reach_the_card_and_the_markdown(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            _run_id, run_dir = _write_run(
                store, [_v_cell("t1", "fake-alpha-1")],
                labels=[
                    rb.GRADING_FAILED_LABEL, rb.STORE_WRITE_FAILED_LABEL,
                    rb.COST_CEILING_LABEL, rb.SPEND_BASIS_LABELS["mixed"],
                ],
            )
            card = _verdict(run_dir)
            text = rb.render_verdict_markdown(card)
            for label in (rb.GRADING_FAILED_LABEL, rb.STORE_WRITE_FAILED_LABEL,
                          rb.COST_CEILING_LABEL, rb.SPEND_BASIS_LABELS["mixed"]):
                self.assertIn(label, card["labels"])
                self.assertIn(label, text)

    def test_the_solved_definition_rides_on_every_card(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            _run_id, run_dir = _write_run(store, [_v_cell("t1", "fake-alpha-1")])
            card = _verdict(run_dir)
            self.assertIn(rb.SOLVED_SOURCE_LABEL, card["labels"])
            self.assertIn(rb.JUDGE_LABEL, card["labels"])
            self.assertIn(rb.STRUCTURAL_LABEL, card["labels"])

    def test_a_solved_earned_beside_test_edits_is_visible_not_buried(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            _run_id, run_dir = _write_run(
                store,
                [_v_cell("t1", "fake-alpha-1", passed=True, touched=["tests/test_m.py"])],
            )
            card = _verdict(run_dir)
            summary = _summary(card, "fake-alpha-1")
            self.assertEqual(summary["solved_with_test_edits"], ["t1"])
            self.assertIn(rb.SOLVED_WITH_TEST_EDITS_LABEL, card["labels"])
            text = rb.render_verdict_markdown(card)
            self.assertIn("solved WITH test-file edits on: t1", text)
            self.assertIn("tests/test_m.py", text)

    def test_a_clean_run_carries_no_test_edit_label(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            _run_id, run_dir = _write_run(store, [_v_cell("t1", "fake-alpha-1", passed=True)])
            self.assertNotIn(rb.SOLVED_WITH_TEST_EDITS_LABEL, _verdict(run_dir)["labels"])

    def test_the_spend_summary_never_prints_dollars_without_a_basis(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            _run_id, run_dir = _write_run(
                store, [_v_cell("t1", "fake-alpha-1")],
                spend={"ceiling_usd": 2.0, "spent_usd": 1.25, "basis": "mixed"},
            )
            text = rb.render_verdict_markdown(_verdict(run_dir))
            self.assertIn("recorded $1.2500 against a $2.0000 ceiling (basis: mixed)", text)
            self.assertIn(rb.SPEND_BASIS_LABELS["mixed"], text)


class VerdictCliTests(unittest.TestCase):
    """`verdict` on the CLI: renders to the run dir and to stdout, folds itself back into the
    envelope, and writes NOTHING anywhere else."""

    def _args(self, run_id, store, *extra):
        return rb.build_parser().parse_args(
            ["verdict", "--run", run_id, "--store-dir", str(store), *extra]
        )

    def test_verdict_md_is_written_under_the_run_dir_only(self):
        real_store = rb.DEFAULT_STORE_DIR
        before_real = sorted(p.name for p in real_store.iterdir()) if real_store.is_dir() else None
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            run_id, run_dir = _write_run(store, [_v_cell("t1", "fake-alpha-1")])
            before = {str(p.relative_to(store)) for p in store.rglob("*")}

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = rb.main(["verdict", "--run", run_id, "--store-dir", str(store)])
            self.assertIsNone(rc)

            after = {str(p.relative_to(store)) for p in store.rglob("*")}
            self.assertEqual(
                after - before, {f"{run_id}/verdict.md"},
                "verdict wrote something other than verdict.md into the store",
            )
            self.assertTrue((run_dir / "verdict.md").exists())
            self.assertIn("# repo-bench verdict", (run_dir / "verdict.md").read_text())
            self.assertIn("# repo-bench verdict", out.getvalue())
            self.assertIn("verdict.md:", out.getvalue())

        after_real = sorted(p.name for p in real_store.iterdir()) if real_store.is_dir() else None
        self.assertEqual(before_real, after_real, "verdict touched the real benchruns store")

    def test_the_verdict_is_folded_back_into_results_json(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            run_id, run_dir = _write_run(
                store, [_v_cell("t1", "fake-alpha-1")], labels=[rb.COST_CEILING_LABEL]
            )
            with contextlib.redirect_stdout(io.StringIO()):
                rb.main(["verdict", "--run", run_id, "--store-dir", str(store)])
            results = json.loads((run_dir / "results.json").read_text())
            self.assertIn("verdict", results)
            verdict = results["verdict"]
            self.assertEqual(verdict["verdict_schema_version"], rb.VERDICT_SCHEMA_VERSION)
            self.assertTrue(verdict["below_floor"])
            self.assertIn(rb._below_floor_label(5), verdict["labels"])
            self.assertIn(rb.COST_CEILING_LABEL, verdict["labels"])
            # the rest of the envelope survived the rewrite untouched
            self.assertEqual(len(results["cells"]), 1)
            self.assertEqual(results["run_id"], run_id)

    def test_rendering_twice_is_stable(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            run_id, run_dir = _write_run(store, [_v_cell("t1", "fake-alpha-1")])
            with contextlib.redirect_stdout(io.StringIO()):
                rb.main(["verdict", "--run", run_id, "--store-dir", str(store)])
                first = (run_dir / "verdict.md").read_text()
                rb.main(["verdict", "--run", run_id, "--store-dir", str(store)])
            self.assertEqual(first, (run_dir / "verdict.md").read_text())

    def test_json_output_is_the_whole_card(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            run_id, _run_dir = _write_run(store, [_v_cell("t1", "fake-alpha-1")])
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rb.main(["verdict", "--run", run_id, "--store-dir", str(store), "--json"])
            card = json.loads(out.getvalue().partition("\nverdict.md:")[0])
            self.assertEqual(card["verdict_schema_version"], rb.VERDICT_SCHEMA_VERSION)
            self.assertTrue(card["below_floor"])

    def test_an_unknown_run_id_exits_2(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            store.mkdir()
            err = io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
                rb.main(["verdict", "--run", "2026-01-01-abcd", "--store-dir", str(store)])
            self.assertEqual(ctx.exception.code, 2)
            self.assertIn("no run", err.getvalue())

    def test_an_unknown_goal_is_refused_by_the_parser(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            run_id, _run_dir = _write_run(store, [_v_cell("t1", "fake-alpha-1")])
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                rb.main([
                    "verdict", "--run", run_id, "--store-dir", str(store), "--goal", "vibes",
                ])

    def test_min_tasks_three_on_the_cli_still_floors_at_five(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            cells = [_v_cell(f"t{i}", "fake-alpha-1") for i in range(4)]
            run_id, run_dir = _write_run(store, cells)
            with contextlib.redirect_stdout(io.StringIO()):
                rb.main([
                    "verdict", "--run", run_id, "--store-dir", str(store), "--min-tasks", "3",
                ])
            verdict = json.loads((run_dir / "results.json").read_text())["verdict"]
            self.assertEqual(verdict["min_tasks"], 5)
            self.assertTrue(verdict["below_floor"])


class VerdictOnARealStubbedRunTests(unittest.TestCase):
    """The whole pipeline, on an envelope this module actually produced — not a synthetic
    fixture. A stubbed dispatch runner fixes the bug for one candidate and not the other; the
    verdict must read `solved` off the tests oracle and only off the tests oracle."""

    def test_a_stubbed_run_renders_a_verdict_that_matches_its_oracles(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            store = td / "store"

            def runner(argv, cwd):
                prompt = argv[-1]
                if "Patch A:" in prompt:
                    return 0, "GRADE A=correct B=correct EQUIVALENT=yes\n" + _canned_result_json()
                model = argv[argv.index("--model") + 1]
                if model.endswith("haiku-4-5") or "haiku" in model:
                    (Path(cwd) / "m.py").write_text("def f():\n    return 2\n")
                else:
                    (Path(cwd) / "notes.md").write_text("gave up\n")
                return 0, _canned_result_json()

            args = _run_args(
                repo, store, "--models", "haiku,sonnet", "--live", "--max-usd", "1000000",
                "--test-cmd", "run-tests", "--mode", "issue-replay",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_run(args, runner=runner, test_runner=_f_returns_2_test_runner)

            run_id = rb.list_runs(store)[0][0]["run_id"]
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rb.main(["verdict", "--run", run_id, "--store-dir", str(store)])
            text = out.getvalue()

            results = json.loads(
                (Path(rb.list_runs(store)[0][0]["path"]) / "results.json").read_text()
            )
            card = results["verdict"]
            order = {row["candidate"]: row for row in card["capability_order"]}
            solver = next(c for c in order if "haiku" in c)
            laggard = next(c for c in order if c != solver)
            self.assertEqual(order[solver]["solved_n"], 1)
            self.assertEqual(order[laggard]["solved_n"], 0,
                             "a judge `correct` produced a `solved` on a real envelope")
            self.assertTrue(card["below_floor"], "a 1-task run claimed routing-grade evidence")
            self.assertIn("BELOW EVIDENCE FLOOR", text)
            self.assertIn(rb.NA, text)
            self.assertIn("similarity", text.lower())


class VerdictReuseTests(unittest.TestCase):
    """PLAN D10/R4 — the published leg and the observed leg are OTHER modules' code. This
    module must call them, never re-implement them, and never edit them."""

    def test_the_published_leg_is_bench_routings(self):
        source = (BIN_DIR / "repo_bench.py").read_text()
        self.assertIn("br.load_benchmarks", source)
        self.assertIn("br.normalize_id", source)
        self.assertIn("br.claude_tier_for_model", source)

    def test_the_observed_leg_is_routing_scorecards(self):
        source = (BIN_DIR / "repo_bench.py").read_text()
        self.assertIn("rs.scan_kits", source)
        self.assertIn("rs.history_tier_stats", source)
        self.assertIn("rs.LIVE_MIN_SAMPLE", source)

    def test_the_benchmarks_path_is_never_re_derived_here(self):
        self.assertEqual(
            rb.default_benchmarks_path(), Path(rb._br().DEFAULT_BENCHMARKS_PATH)
        )
        # The filename never appears as a STRING LITERAL here — the only mention is prose in
        # a docstring naming what the reused constant points at.
        source = (BIN_DIR / "repo_bench.py").read_text()
        self.assertNotIn('"benchmarks.aa.json"', source)
        self.assertNotIn("'benchmarks.aa.json'", source)

    def test_the_reused_modules_are_loaded_lazily(self):
        # A store-only command must not drag the ledger/benchmark machinery in: a freshly
        # imported module holds neither handle until something actually asks for one.
        fresh = _load("repo_bench")
        self.assertIsNone(fresh._BR_MOD)
        self.assertIsNone(fresh._RS_MOD)
        self.assertTrue(hasattr(fresh._br(), "load_benchmarks"))
        self.assertTrue(hasattr(fresh._rs(), "scan_kits"))
        self.assertIsNotNone(fresh._BR_MOD)


class StoreWriteFailureEnvelopeTests(unittest.TestCase):
    """T7R-informational, carried into T8: the store's sibling writes are guarded, and a
    failure there must still leave a labelled envelope. Correct in code since T7R, asserted
    by no test until now."""

    def test_a_failing_task_record_write_still_leaves_a_labelled_envelope(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            store = td / "store"

            def runner(argv, cwd):
                # Break the run dir's `tasks/` directory from inside the loop: the buffered
                # task records are written after the last dispatch, and that write must fail
                # WITHOUT costing the envelope.
                tasks_dir = Path(cwd).parents[1] / "tasks"
                if tasks_dir.is_dir():
                    shutil.rmtree(tasks_dir)
                    tasks_dir.write_text("not a directory any more\n")
                (Path(cwd) / "candidate_fix.py").write_text("# real, paid-for work\n")
                return 0, _canned_result_json()

            args = _run_args(repo, store, "--live", "--max-usd", "1000000")
            with contextlib.redirect_stdout(io.StringIO()):
                rc = rb.cmd_run(args, runner=runner)

            self.assertEqual(rc, 0, "a store-write failure is a labelled outcome, not a crash")
            run_dir = Path(rb.list_runs(store)[0][0]["path"])
            results = json.loads((run_dir / "results.json").read_text())
            self.assertIn(rb.STORE_WRITE_FAILED_LABEL, results["labels"])
            self.assertTrue(any(rb.STORE_WRITE_FAILED_NOTE in n for n in results["notes"]))
            self.assertGreater(results["spend"]["spent_usd"], 0.0)
            self.assertIn(rb.SPEND_BASIS_LABELS[results["spend"]["basis"]], results["labels"])
            self.assertTrue(results["cells"], "the measured cells were lost with the sibling")

    def test_that_label_survives_into_the_verdict(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            _run_id, run_dir = _write_run(
                store, [_v_cell("t1", "fake-alpha-1")], labels=[rb.STORE_WRITE_FAILED_LABEL]
            )
            card = _verdict(run_dir)
            self.assertIn(rb.STORE_WRITE_FAILED_LABEL, card["labels"])
            self.assertIn(rb.STORE_WRITE_FAILED_LABEL, rb.render_verdict_markdown(card))


# ---------------------------------------------------------------------------------------------
# T9 -- `apply` + `list`: opt-in prefs write, staleness-guarded. PLAN D9's law lives here:
# `apply` is the ONLY path by which a measurement changes routing, and it must refuse a
# below-floor or stale verdict outright. Fixtures are hand-built `results.json` envelopes in
# TEMP stores (GUARDRAILS sanctions this for reader tests); every prefs write in this block
# targets a TEMP `--prefs-path`, never the real gitignored `prefs/repo-bench.json`.


class BuildPrefsPayloadTests(unittest.TestCase):
    """`build_prefs_payload` in isolation: the pinned schema, labels LIFTED verbatim, and id
    canonicalization through `cost_report.match_model` (FAKE_PRICING, never a real id)."""

    def test_happy_path_shape(self):
        card = {
            "run_id": "2026-01-01-abcd",
            "repo": "/some/target",
            "tier_map": {
                "slots": {"strong": "fake-gamma-1", "mid": "fake-beta-1", "weak": "fake-alpha-1"},
            },
            "daily_driver": {"pick": "fake-alpha-1"},
            "labels": ["some-label", rb.GRADING_FAILED_LABEL],
        }
        payload = rb.build_prefs_payload(card, FAKE_PRICING)
        self.assertEqual(payload["schema_version"], rb.PREFS_SCHEMA_VERSION)
        self.assertEqual(payload["source_run"], "2026-01-01-abcd")
        self.assertEqual(payload["repo"], "/some/target")
        self.assertEqual(
            payload["tiers"],
            {"strong": "fake-gamma-1", "mid": "fake-beta-1", "weak": "fake-alpha-1"},
        )
        self.assertEqual(payload["daily_driver"], "fake-alpha-1")
        self.assertEqual(payload["labels"], ["some-label", rb.GRADING_FAILED_LABEL])
        self.assertIn("T", payload["applied_at"])  # an ISO timestamp, not a bare date

    def test_empty_tier_map_and_no_daily_driver_pick_render_none(self):
        card = {
            "run_id": "r1", "repo": "/x", "tier_map": {"slots": {}},
            "daily_driver": {"pick": None}, "labels": [],
        }
        payload = rb.build_prefs_payload(card, FAKE_PRICING)
        self.assertEqual(payload["tiers"], {"strong": None, "mid": None, "weak": None})
        self.assertIsNone(payload["daily_driver"])

    def test_store_write_failed_label_survives_lifted_verbatim(self):
        card = {
            "run_id": "r1", "repo": "/x",
            "tier_map": {"slots": {"strong": "fake-gamma-1", "mid": None, "weak": None}},
            "daily_driver": {"pick": None},
            "labels": [rb.STORE_WRITE_FAILED_LABEL, rb.GRADING_FAILED_LABEL],
        }
        payload = rb.build_prefs_payload(card, FAKE_PRICING)
        self.assertIn(rb.STORE_WRITE_FAILED_LABEL, payload["labels"])
        self.assertIn(rb.GRADING_FAILED_LABEL, payload["labels"])


class ApplyVerdictTests(unittest.TestCase):
    """`apply_verdict` (the engine core `cmd_apply` wraps): read + refuse + atomic write,
    exercised directly with FAKE_PRICING and temp prefs paths -- never the real
    `data/pricing.json` staleness surface or the real `prefs/` store."""

    def test_happy_path_writes_the_pinned_schema(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs" / "repo-bench.json"
            run_id, run_dir = _write_run_with_verdict(
                store,
                tier_slots={"strong": "fake-gamma-1", "mid": "fake-beta-1", "weak": "fake-alpha-1"},
                daily_driver_pick="fake-alpha-1",
                labels=["a-label"],
                repo="/some/target",
            )
            payload, old = rb.apply_verdict(run_dir, prefs_path, FAKE_PRICING)
            self.assertIsNone(old)
            self.assertTrue(prefs_path.exists())
            on_disk = json.loads(prefs_path.read_text())
            self.assertEqual(on_disk, payload)
            self.assertEqual(payload["schema_version"], rb.PREFS_SCHEMA_VERSION)
            self.assertEqual(payload["source_run"], run_id)
            self.assertEqual(payload["repo"], "/some/target")
            self.assertEqual(
                payload["tiers"],
                {"strong": "fake-gamma-1", "mid": "fake-beta-1", "weak": "fake-alpha-1"},
            )
            self.assertEqual(payload["daily_driver"], "fake-alpha-1")
            self.assertIn("a-label", payload["labels"])
            self.assertFalse((prefs_path.parent / (prefs_path.name + ".tmp")).exists())

    def test_no_verdict_recorded_refuses(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            _run_id, run_dir = _write_run(store, [_v_cell("t1", "fake-alpha-1")])
            with self.assertRaises(ValueError) as ctx:
                rb.apply_verdict(run_dir, prefs_path, FAKE_PRICING)
            self.assertIn("run verdict first", str(ctx.exception))
            self.assertFalse(prefs_path.exists())

    def test_below_floor_verdict_refuses(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            _run_id, run_dir = _write_run_with_verdict(
                store,
                tier_slots={"strong": "fake-gamma-1", "mid": None, "weak": None},
                daily_driver_pick=None,
                below_floor=True,
            )
            with self.assertRaises(ValueError) as ctx:
                rb.apply_verdict(run_dir, prefs_path, FAKE_PRICING)
            self.assertIn("below-floor verdict is never applied", str(ctx.exception))
            self.assertFalse(prefs_path.exists())

    def test_below_floor_key_absent_refuses_the_gate_must_fail_closed(self):
        """Defect 1: `.get("below_floor")` used to treat an ABSENT key exactly like `False`
        -- a full prefs payload got written from an incomplete card, no refusal. The gate
        must instead require `below_floor` to be AFFIRMATIVELY `False`."""
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            verdict = {
                "verdict_schema_version": rb.VERDICT_SCHEMA_VERSION,
                "goal": "both",
                "min_tasks": rb.MIN_EVIDENCE_TASKS,
                # below_floor deliberately OMITTED entirely
                "below_floor_label": None,
                "rule": "synthetic rule text",
                "capability_order": [],
                "tier_map": {
                    "slots": {"strong": "fake-gamma-1", "mid": "fake-beta-1", "weak": "fake-alpha-1"},
                    "nearest_neighbors": {}, "role_gloss": {}, "notes": [],
                },
                "daily_driver": {"pick": "fake-alpha-1", "notes": []},
                "three_legs": [], "disagreements": [], "labels": [], "notes": [],
            }
            _run_id, run_dir = _write_run_with_raw_verdict(store, verdict)
            with self.assertRaises(ValueError) as ctx:
                rb.apply_verdict(run_dir, prefs_path, FAKE_PRICING)
            self.assertIn("below_floor", str(ctx.exception))
            self.assertFalse(prefs_path.exists(), "NO REFUSAL -- a below-floor-absent card was applied")

    def test_below_floor_none_refuses(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            verdict = {
                "below_floor": None,
                "tier_map": {"slots": {"strong": "fake-gamma-1", "mid": None, "weak": None}},
                "daily_driver": {"pick": None},
            }
            _run_id, run_dir = _write_run_with_raw_verdict(store, verdict)
            with self.assertRaises(ValueError) as ctx:
                rb.apply_verdict(run_dir, prefs_path, FAKE_PRICING)
            self.assertIn("below_floor", str(ctx.exception))
            self.assertFalse(prefs_path.exists())

    def test_below_floor_non_bool_string_refuses(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            verdict = {
                "below_floor": "false",  # a string, not a bool -- must not be truthy-coerced
                "tier_map": {"slots": {"strong": "fake-gamma-1", "mid": None, "weak": None}},
                "daily_driver": {"pick": None},
            }
            _run_id, run_dir = _write_run_with_raw_verdict(store, verdict)
            with self.assertRaises(ValueError) as ctx:
                rb.apply_verdict(run_dir, prefs_path, FAKE_PRICING)
            self.assertIn("below_floor", str(ctx.exception))
            self.assertFalse(prefs_path.exists())

    def test_non_dict_verdict_refuses_cleanly(self):
        """A non-dict `verdict` value must refuse with a plain ValueError, never an opaque
        AttributeError from calling `.get()` on a string/list."""
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            _run_id, run_dir = _write_run_with_raw_verdict(store, "not-a-dict-verdict")
            with self.assertRaises(ValueError) as ctx:
                rb.apply_verdict(run_dir, prefs_path, FAKE_PRICING)
            self.assertNotIsInstance(ctx.exception, AttributeError)
            self.assertFalse(prefs_path.exists())

    def test_non_dict_verdict_list_refuses_cleanly(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            _run_id, run_dir = _write_run_with_raw_verdict(store, ["below_floor", False])
            with self.assertRaises(ValueError):
                rb.apply_verdict(run_dir, prefs_path, FAKE_PRICING)
            self.assertFalse(prefs_path.exists())

    def test_tier_map_missing_slots_refuses_as_malformed(self):
        """Defect 2: a `tier_map` present but shaped differently (e.g. flat `{"strong": id,
        ...}` with no `"slots"` wrapper) used to make `slots` resolve to `{}` and the staleness
        loop iterate over nothing -- a check that verified nothing reported success. A
        wrongly-shaped `tier_map` must instead refuse as malformed."""
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            verdict = {
                "below_floor": False,
                "tier_map": {"strong": "fake-gamma-1", "mid": "fake-beta-1", "weak": "fake-alpha-1"},
                "daily_driver": {"pick": "fake-alpha-1"},
            }
            _run_id, run_dir = _write_run_with_raw_verdict(store, verdict)
            with self.assertRaises(ValueError) as ctx:
                rb.apply_verdict(run_dir, prefs_path, FAKE_PRICING)
            self.assertIn("tier_map", str(ctx.exception))
            self.assertFalse(prefs_path.exists())

    def test_wrongly_shaped_tier_map_never_clobbers_an_existing_prefs_file(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            good_id, good_dir = _write_run_with_verdict(
                store,
                tier_slots={"strong": "fake-gamma-1", "mid": "fake-beta-1", "weak": "fake-alpha-1"},
                daily_driver_pick="fake-alpha-1",
            )
            rb.apply_verdict(good_dir, prefs_path, FAKE_PRICING)
            before = prefs_path.read_text()

            bad_verdict = {
                "below_floor": False,
                "tier_map": {"strong": "fake-gamma-1", "mid": "fake-beta-1", "weak": "fake-alpha-1"},
                "daily_driver": {"pick": "fake-alpha-1"},
            }
            _bad_id, bad_dir = _write_run_with_raw_verdict(store, bad_verdict)
            with self.assertRaises(ValueError):
                rb.apply_verdict(bad_dir, prefs_path, FAKE_PRICING)
            after = prefs_path.read_text()
            self.assertEqual(before, after, "a malformed card overwrote a good prefs file")
            after_payload = json.loads(after)
            self.assertIsNotNone(after_payload["tiers"]["strong"], "prefs replaced with all-None tiers")

    def test_daily_driver_wrong_shape_refuses_as_malformed(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            verdict = {
                "below_floor": False,
                "tier_map": {"slots": {"strong": "fake-gamma-1", "mid": None, "weak": None}},
                "daily_driver": "fake-alpha-1",  # a bare string, not {"pick": ...}
            }
            _run_id, run_dir = _write_run_with_raw_verdict(store, verdict)
            with self.assertRaises(ValueError) as ctx:
                rb.apply_verdict(run_dir, prefs_path, FAKE_PRICING)
            self.assertIn("daily_driver", str(ctx.exception))
            self.assertFalse(prefs_path.exists())

    def test_stale_id_under_wrongly_shaped_tier_map_refuses(self):
        """The staleness check must not 'pass' by finding nothing to check: a stale id placed
        directly under a wrongly-shaped `tier_map` (no `"slots"` wrapper) must still refuse,
        not slip through by being structurally unreachable."""
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            verdict = {
                "below_floor": False,
                "tier_map": {"strong": "fake-retired-9", "mid": None, "weak": None},
                "daily_driver": {"pick": None},
            }
            _run_id, run_dir = _write_run_with_raw_verdict(store, verdict)
            with self.assertRaises(ValueError):
                rb.apply_verdict(run_dir, prefs_path, FAKE_PRICING)
            self.assertFalse(prefs_path.exists())

    def test_tier_map_none_is_legitimate_not_malformed(self):
        """A daily-driver-only run legitimately has `tier_map: None` (build_verdict omits it
        when `goal` excludes tiers) -- that must NOT be treated as malformed."""
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            verdict = {
                "below_floor": False,
                "tier_map": None,
                "daily_driver": {"pick": "fake-alpha-1"},
            }
            _run_id, run_dir = _write_run_with_raw_verdict(store, verdict)
            payload, _old = rb.apply_verdict(run_dir, prefs_path, FAKE_PRICING)
            self.assertEqual(payload["tiers"], {"strong": None, "mid": None, "weak": None})
            self.assertEqual(payload["daily_driver"], "fake-alpha-1")

    def test_daily_driver_none_is_legitimate_not_malformed(self):
        """A tiers-only run legitimately has `daily_driver: None`."""
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            verdict = {
                "below_floor": False,
                "tier_map": {"slots": {"strong": "fake-gamma-1", "mid": None, "weak": None}},
                "daily_driver": None,
            }
            _run_id, run_dir = _write_run_with_raw_verdict(store, verdict)
            payload, _old = rb.apply_verdict(run_dir, prefs_path, FAKE_PRICING)
            self.assertEqual(payload["tiers"]["strong"], "fake-gamma-1")
            self.assertIsNone(payload["daily_driver"])

    def test_stale_tier_id_refuses(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            _run_id, run_dir = _write_run_with_verdict(
                store,
                tier_slots={
                    "strong": "fake-retired-9", "mid": "fake-beta-1", "weak": "fake-alpha-1",
                },
                daily_driver_pick="fake-alpha-1",
            )
            with self.assertRaises(ValueError) as ctx:
                rb.apply_verdict(run_dir, prefs_path, FAKE_PRICING)
            self.assertIn("fake-retired-9", str(ctx.exception))
            self.assertIn("no longer in data/pricing.json", str(ctx.exception))
            self.assertFalse(prefs_path.exists())

    def test_stale_daily_driver_id_refuses(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            _run_id, run_dir = _write_run_with_verdict(
                store,
                tier_slots={
                    "strong": "fake-gamma-1", "mid": "fake-beta-1", "weak": "fake-alpha-1",
                },
                daily_driver_pick="fake-retired-9",
            )
            with self.assertRaises(ValueError) as ctx:
                rb.apply_verdict(run_dir, prefs_path, FAKE_PRICING)
            self.assertIn("fake-retired-9", str(ctx.exception))
            self.assertFalse(prefs_path.exists())

    def test_reapply_overwrites_with_a_new_applied_at(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            _run_id, run_dir = _write_run_with_verdict(
                store,
                tier_slots={
                    "strong": "fake-gamma-1", "mid": "fake-beta-1", "weak": "fake-alpha-1",
                },
                daily_driver_pick="fake-alpha-1",
            )
            first, old1 = rb.apply_verdict(run_dir, prefs_path, FAKE_PRICING)
            self.assertIsNone(old1)
            second, old2 = rb.apply_verdict(run_dir, prefs_path, FAKE_PRICING)
            self.assertEqual(old2, first)
            self.assertNotEqual(first["applied_at"], second["applied_at"])
            on_disk = json.loads(prefs_path.read_text())
            self.assertEqual(on_disk, second)

    def test_no_results_json_at_all_raises_file_not_found(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            _run_id, run_dir = rb.new_run_dir(store)  # meta.json only, no results.json
            with self.assertRaises(FileNotFoundError):
                rb.apply_verdict(run_dir, prefs_path, FAKE_PRICING)


class ApplyCliTests(unittest.TestCase):
    """`apply` on the CLI: argument wiring and the printed receipt. `cmd_apply` prices
    against the REAL `data/pricing.json` (like every other subcommand's default path), so
    the happy-path test derives real ids from `cost_report.load_pricing()` at run time --
    never a hardcoded literal -- rather than reuse FAKE_PRICING's ids, which the real file
    does not contain."""

    def _real_ids(self, n):
        pricing = rb._cr().load_pricing()
        ids = list(pricing["models"])
        self.assertGreaterEqual(
            len(ids), n, "data/pricing.json has fewer models than this test needs"
        )
        return ids[:n]

    def test_apply_via_cli_writes_prefs_and_prints_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs" / "repo-bench.json"
            strong, mid, weak = self._real_ids(3)
            run_id, _run_dir = _write_run_with_verdict(
                store,
                tier_slots={"strong": strong, "mid": mid, "weak": weak},
                daily_driver_pick=weak,
                repo="/some/target",
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = rb.main([
                    "apply", "--run", run_id, "--store-dir", str(store),
                    "--prefs-path", str(prefs_path),
                ])
            self.assertIsNone(rc)
            text = out.getvalue()
            self.assertIn(run_id, text)
            self.assertIn(str(prefs_path), text)
            payload = json.loads(prefs_path.read_text())
            self.assertEqual(payload["source_run"], run_id)
            self.assertEqual(payload["tiers"]["strong"], strong)

    def test_unknown_run_id_exits_2(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            store.mkdir()
            prefs_path = Path(td) / "prefs.json"
            err = io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
                rb.main([
                    "apply", "--run", "2026-01-01-abcd", "--store-dir", str(store),
                    "--prefs-path", str(prefs_path),
                ])
            self.assertEqual(ctx.exception.code, 2)
            self.assertIn("no run", err.getvalue())
            self.assertFalse(prefs_path.exists())

    def test_missing_run_flag_is_refused_by_the_parser(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
            rb.main(["apply"])
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("--run", err.getvalue())

    def test_below_floor_via_cli_exits_2_and_never_touches_prefs(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            run_id, _run_dir = _write_run_with_verdict(
                store,
                tier_slots={"strong": None, "mid": None, "weak": None},
                daily_driver_pick=None,
                below_floor=True,
            )
            err = io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
                rb.main([
                    "apply", "--run", run_id, "--store-dir", str(store),
                    "--prefs-path", str(prefs_path),
                ])
            self.assertEqual(ctx.exception.code, 2)
            self.assertIn("below-floor verdict is never applied", err.getvalue())
            self.assertFalse(prefs_path.exists())

    def test_below_floor_absent_via_cli_exits_2_and_never_touches_prefs(self):
        """Defect 1 at the CLI boundary: a card with `below_floor` entirely absent must exit
        2, print a refusal, and leave no prefs file -- not silently apply."""
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            verdict = {
                "below_floor_label": None,
                "tier_map": {
                    "slots": {"strong": "fake-gamma-1", "mid": "fake-beta-1", "weak": "fake-alpha-1"},
                },
                "daily_driver": {"pick": "fake-alpha-1"},
            }
            run_id, _run_dir = _write_run_with_raw_verdict(store, verdict)
            err = io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
                rb.main([
                    "apply", "--run", run_id, "--store-dir", str(store),
                    "--prefs-path", str(prefs_path),
                ])
            self.assertEqual(ctx.exception.code, 2)
            self.assertIn("below_floor", err.getvalue())
            self.assertFalse(
                prefs_path.exists(),
                "NO REFUSAL -- a below-floor-absent card was applied via the CLI",
            )

    def test_apply_never_writes_the_real_prefs_file(self):
        real_prefs = rb.DEFAULT_PREFS_PATH
        before_existed = real_prefs.exists()
        before = real_prefs.read_text() if before_existed else None
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            strong, mid, weak = self._real_ids(3)
            run_id, _run_dir = _write_run_with_verdict(
                store, tier_slots={"strong": strong, "mid": mid, "weak": weak},
                daily_driver_pick=weak,
            )
            with contextlib.redirect_stdout(io.StringIO()):
                rb.main([
                    "apply", "--run", run_id, "--store-dir", str(store),
                    "--prefs-path", str(prefs_path),
                ])
        after_existed = real_prefs.exists()
        after = real_prefs.read_text() if after_existed else None
        self.assertEqual(before_existed, after_existed)
        self.assertEqual(before, after)


class ListRenderingTests(unittest.TestCase):
    """T9's extension of `list`: repo/mode/candidates/spend/verdict-presence/below-floor/
    applied, all read tolerantly, and never an invented dollar figure for a run with no
    spend record."""

    def test_list_shows_run_fields_and_dash_for_missing_spend(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            run_id, _run_dir = _write_run(
                store, [_v_cell("t1", "fake-alpha-1")], repo="/some/target",
                spend={"ceiling_usd": 5.0, "spent_usd": 1.2345, "basis": "actual"},
            )
            bare_id, _bare_dir = rb.new_run_dir(store)  # meta.json only

            rows, _notes = rb.list_runs(store)
            by_id = {r["run_id"]: r for r in rows}
            self.assertEqual(by_id[run_id]["repo"], "/some/target")
            self.assertEqual(by_id[run_id]["mode"], "issue-replay")
            self.assertEqual(by_id[run_id]["spend"]["spent_usd"], 1.2345)
            self.assertFalse(by_id[run_id]["verdict_present"])
            self.assertIsNone(by_id[run_id]["below_floor"])
            self.assertIsNone(by_id[bare_id]["repo"])
            self.assertIsNone(by_id[bare_id]["spend"])
            self.assertFalse(by_id[bare_id]["verdict_present"])

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rb.main(["list", "--store-dir", str(store)])
            text = out.getvalue()
            self.assertIn("$1.2345 (actual)", text)
            self.assertIn(rb.NA, text)  # the bare run's spend/verdict cells, never $0.0000

    def test_list_shows_verdict_present_and_below_floor(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            run_id, _run_dir = _write_run_with_verdict(
                store, tier_slots={"strong": "fake-gamma-1", "mid": None, "weak": None},
                daily_driver_pick=None, below_floor=True,
            )
            rows, _notes = rb.list_runs(store)
            row = next(r for r in rows if r["run_id"] == run_id)
            self.assertTrue(row["verdict_present"])
            self.assertTrue(row["below_floor"])

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rb.main(["list", "--store-dir", str(store)])
            text = out.getvalue()
            self.assertIn("verdict: yes", text)
            self.assertIn("below-floor: yes", text)

    def test_list_shows_applied_marker_after_apply(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            tiers = {"strong": "fake-gamma-1", "mid": "fake-beta-1", "weak": "fake-alpha-1"}
            run_id, run_dir = _write_run_with_verdict(
                store, tier_slots=tiers, daily_driver_pick="fake-alpha-1",
            )
            other_id, _other_dir = _write_run_with_verdict(
                store, tier_slots=tiers, daily_driver_pick="fake-alpha-1",
            )
            rb.apply_verdict(run_dir, prefs_path, FAKE_PRICING)

            # list_runs itself is prefs-agnostic -- "applied" is a `cmd_list`-layer join
            rows, _notes = rb.list_runs(store)
            self.assertNotIn("applied", rows[0])

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = rb.main([
                    "list", "--store-dir", str(store), "--prefs-path", str(prefs_path), "--json",
                ])
            self.assertIsNone(rc)
            payload = json.loads(out.getvalue())
            applied_by_id = {r["run_id"]: r["applied"] for r in payload["runs"]}
            self.assertTrue(applied_by_id[run_id])
            self.assertFalse(applied_by_id[other_id])

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rb.main(["list", "--store-dir", str(store), "--prefs-path", str(prefs_path)])
            text = out.getvalue()
            self.assertIn("applied: yes", text)
            self.assertIn("applied: no", text)

    def test_list_tolerates_a_rogue_run_dir_with_a_broken_results_json(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            run_id, run_dir = rb.new_run_dir(store)
            (run_dir / "results.json").write_text("{not json at all")

            rows, notes = rb.list_runs(store)
            row = next(r for r in rows if r["run_id"] == run_id)
            self.assertIsNone(row["repo"])
            self.assertFalse(row["verdict_present"])
            self.assertEqual(rows, [row], notes)  # still listed, not dropped

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = rb.main(["list", "--store-dir", str(store)])
            self.assertIsNone(rc)
            self.assertIn(run_id, out.getvalue())

    def test_list_tolerates_a_results_json_that_is_not_an_object(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            run_id, run_dir = rb.new_run_dir(store)
            (run_dir / "results.json").write_text("[1, 2, 3]")

            rows, _notes = rb.list_runs(store)
            row = next(r for r in rows if r["run_id"] == run_id)
            self.assertIsNone(row["repo"])
            self.assertFalse(row["verdict_present"])

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = rb.main(["list", "--store-dir", str(store)])
            self.assertIsNone(rc)


def build_harness_fixture_repo(root):
    """T12R/F1's fixture: a general-mode repo whose test command depends on files NO test
    pattern names.

    `run_tests.py` is the harness the command invokes and `alt.py` is an ordinary module —
    `_matches_test_pattern` returns False for both, which is the entirety of F1. `calc.py`
    carries the single `>=` mutation site the general miner will find. Returns HEAD.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    (root / "calc.py").write_text(
        "def classify(x):\n"
        "    if x >= 10:\n"
        '        return "big"\n'
        '    return "small"\n'
    )
    (root / "alt.py").write_text('MODE = "stock"\n')
    (root / "run_tests.py").write_text('HARNESS = "stock"\n')
    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_calc.py").write_text("# the repo's own visible test\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "c1: classify, its harness and a sibling module")
    return _git(root, "rev-parse", "HEAD").strip()


def _harness_test_runner(cmd, cwd):
    """STUB `test_runner` that reads the tree it is handed — no subprocess, no model.

    It really does depend on the harness, on a `conftest.py`, and on `alt.py`, so every
    forgery below is a forgery rather than a pantomime; absent all of those it grades the
    actual bug.
    """
    cwd = Path(cwd)
    harness = cwd / "run_tests.py"
    if harness.exists() and "FORGED" in harness.read_text():
        return 0, "OK (the harness was rewritten)"
    if (cwd / "conftest.py").exists():
        return 0, "OK (a planted conftest short-circuited the run)"
    alt = cwd / "alt.py"
    if alt.exists() and "PATCHED" in alt.read_text():
        return 0, "OK (alt.py supplied the behaviour)"
    calc = cwd / "calc.py"
    if not calc.exists():
        return 1, "FAIL: calc.py is missing"
    return (
        (1, "FAIL: classify(10) is no longer big") if "x > 10" in calc.read_text()
        else (0, "OK")
    )


def _candidate_that(mutate):
    """A dispatch runner that applies `mutate(cwd)` in a candidate sandbox and nothing in the
    judge's throwaway cwd (which has no `calc.py`)."""
    def runner(argv, cwd):
        cwd = Path(cwd)
        if not (cwd / "calc.py").exists():
            return 0, _canned_result_json()
        mutate(cwd)
        return 0, _canned_result_json()
    return runner


def _run_general_harness_fixture(td, mutate, *, keep_work=False, no_full_patch_check=False):
    """One stubbed general-mode run over `build_harness_fixture_repo` -> (results, run_dir).

    `no_full_patch_check` (T20) switches the full-patch DIAGNOSTIC off, which is how the
    isolation tests obtain the pre-T20 behaviour to compare against byte for byte.
    """
    td = Path(td)
    repo = td / "target"
    build_harness_fixture_repo(repo)
    store = td / "store"
    argv = [
        "run", "--repo", str(repo), "--models", "haiku", "--mode", "general",
        "--test-cmd", "harness-tests", "--store-dir", str(store),
        "--live", "--max-usd", "1000000",
    ]
    if keep_work:
        argv.append("--keep-work")
    if no_full_patch_check:
        argv.append("--no-full-patch-check")
    args = rb.build_parser().parse_args(argv)
    with contextlib.redirect_stdout(io.StringIO()):
        rb.cmd_run(args, runner=_candidate_that(mutate), test_runner=_harness_test_runner)
    run_dir = Path(rb.list_runs(store)[0][0]["path"])
    return json.loads((run_dir / "results.json").read_text()), run_dir


class HarnessForgeryTests(unittest.TestCase):
    """F1 (Phase 4 review) — THE THIRD INSTANCE OF ONE SHAPE.

    Phase 2 protected the ANSWER. Phase 3 protected the ORACLE's test-PATTERN files. Phase 4
    found that the test HARNESS is not a test-pattern path: a candidate that touched no module
    and no test-pattern file, and only rewrote the file `--test-cmd` invokes, swept `solved`,
    cleared the D7 floor and was APPLIED — with `candidate_touched_tests` empty, so T7R's
    visibility net never saw it. These tests pin the structural close (revert everything
    changed outside the REFERENCE PATCH's scope) and, just as importantly, pin the false
    negative it costs as VISIBLE rather than silent.
    """

    def test_the_harness_is_not_a_test_pattern_path(self):
        """The premise, asserted rather than assumed — if this ever goes True the fix below
        is being credited to the wrong mechanism."""
        for name in (
            "conftest.py", "run_tests.py", "Makefile", "tox.ini", "pytest.ini",
            "setup.py", "noxfile.py", "pyproject.toml",
        ):
            self.assertFalse(
                rb._matches_test_pattern(name, rb.DEFAULT_TEST_PATTERNS),
                f"{name} matches a test pattern — F1's premise no longer holds",
            )

    def test_rewriting_the_test_command_entry_point_cannot_earn_solved(self):
        """The Phase 4 reviewer's own forgery, verbatim: rewrite the file `--test-cmd` invokes
        to exit 0, touch no module and no test-pattern path. It earned 6/6 `solved`, cleared
        the D7 floor and was applied to a prefs file."""
        with tempfile.TemporaryDirectory() as td:
            results, run_dir = _run_general_harness_fixture(
                td,
                lambda cwd: (cwd / "run_tests.py").write_text(
                    "import sys; sys.exit(0)  # FORGED\n"
                ),
                keep_work=True,
            )
            cells = [c for c in results["cells"] if not c["skipped"]]
            self.assertTrue(cells, results["notes"])
            cell = cells[0]
            self.assertTrue(cell["oracles"]["tests"]["available"], cell["oracles"]["tests"])
            self.assertFalse(
                cell["oracles"]["tests"]["passed"],
                "rewriting the file --test-cmd invokes still earned `solved`",
            )
            # T7R's net is genuinely blind to this — which is why F1 needed its own.
            self.assertEqual(cell["candidate_touched_tests"], [])
            self.assertEqual(cell["candidate_modified_out_of_scope"], ["run_tests.py"])
            self.assertIn(
                rb.CANDIDATE_OUT_OF_SCOPE_NOTE.split("—")[0].strip(),
                cell["oracles"]["tests"]["notes"],
            )
            self.assertTrue(
                any(rb.CANDIDATE_OUT_OF_SCOPE_NOTE in n for n in results["notes"]),
                results["notes"],
            )

            # …and the same tree really would have graded GREEN under the PRE-T12R algorithm.
            # It touched no test-pattern path at all, so T7R's test-surface restore was a
            # no-op on it and `_old_style_grade` reproduces exactly what the cell would have
            # scored: a test that only asserts the new behaviour cannot show the hole was real.
            task = json.loads(next((run_dir / "tasks").glob("*.json")).read_text())
            sandbox = next(
                p for p in (run_dir / "work").iterdir()
                if p.is_dir() and p.name.startswith("cell-")
            )
            self.assertEqual(
                _harness_test_runner("harness-tests", str(sandbox))[0], 0,
                "the forgery no longer forges anything — this test proves nothing",
            )
            self.assertEqual(task["mode"], "general")

    def test_a_created_conftest_outside_the_reference_scope_is_removed(self):
        """The oracle's own docstring claimed a candidate-authored `conftest.py` was already
        in the closed class. It was not: `conftest.py` matches no test pattern, so it was
        neither restored nor deleted, and it reached grading intact."""
        with tempfile.TemporaryDirectory() as td:
            results, _run_dir = _run_general_harness_fixture(
                td, lambda cwd: (cwd / "conftest.py").write_text("import sys\n")
            )
            cell = next(c for c in results["cells"] if not c["skipped"])
            self.assertFalse(
                cell["oracles"]["tests"]["passed"], "a planted conftest.py earned `solved`"
            )
            self.assertEqual(cell["candidate_touched_tests"], [])
            self.assertEqual(cell["candidate_modified_out_of_scope"], ["conftest.py"])

    def test_a_gitignored_creation_cannot_reach_the_substrate_though_no_patch_names_it(self):
        """WHY THE WHITELIST BEATS ANY BLACKLIST, in one case.

        `capture_patch` runs `git add -A` inside a repo the candidate controls, so a candidate
        that adds a line to `.gitignore` and then writes the file it wants to survive produces
        a patch that never names it. A blacklist that reverted "what the patch says the
        candidate changed" would have missed it — the fourth miss in this same chain. The
        substrate never contains it for a reason that needs no detection at all: it was never
        applied.

        Also pins the honest limit of the RECORD: `candidate_modified_out_of_scope` is read off
        the patch, so this hidden file is absent from it. That is evidence being incomplete,
        not the guarantee leaking — which is exactly what
        `CANDIDATE_OUT_OF_SCOPE_EVIDENCE_NOTE` says out loud.
        """
        def mutate(cwd):
            (cwd / ".gitignore").write_text("conftest.py\n")
            (cwd / "conftest.py").write_text("import sys\n")

        with tempfile.TemporaryDirectory() as td:
            results, _run_dir = _run_general_harness_fixture(td, mutate)
            cell = next(c for c in results["cells"] if not c["skipped"])
            patched_paths = {
                path for path, _text in rb._split_diff_by_file(cell["patch"] or "")
            }
            self.assertNotIn(
                "conftest.py", patched_paths,
                "the fixture is wrong: the captured patch DOES carry the hidden file",
            )
            self.assertFalse(
                cell["oracles"]["tests"]["passed"],
                "a patch-invisible planted conftest.py earned `solved`",
            )
            self.assertNotIn(
                "conftest.py", cell["candidate_modified_out_of_scope"],
                "the record claims completeness the captured patch cannot give it",
            )
            self.assertIn(".gitignore", cell["candidate_modified_out_of_scope"])

    def test_deleting_an_out_of_scope_file_is_never_applied_either(self):
        """A deletion is a modification. Removing a harness file can turn a suite green just
        as writing one can — and an out-of-scope deletion is simply not part of the substrate,
        so the base version is there because it was never taken away."""
        with tempfile.TemporaryDirectory() as td:
            results, _run_dir = _run_general_harness_fixture(
                td, lambda cwd: (cwd / "run_tests.py").unlink()
            )
            cell = next(c for c in results["cells"] if not c["skipped"])
            self.assertFalse(cell["oracles"]["tests"]["passed"])
            self.assertIn("run_tests.py", cell["candidate_modified_out_of_scope"])

    def test_a_genuine_in_scope_fix_still_reads_solved(self):
        """The other half: the sweep must not make solving impossible. The mutated file IS the
        reference patch's scope, so a real repair is untouched and grades green with an
        explicitly EMPTY out-of-scope list — measured, not absent."""
        def mutate(cwd):
            calc = cwd / "calc.py"
            calc.write_text(calc.read_text().replace("x > 10", "x >= 10"))

        with tempfile.TemporaryDirectory() as td:
            results, _run_dir = _run_general_harness_fixture(td, mutate)
            cell = next(c for c in results["cells"] if not c["skipped"])
            self.assertTrue(cell["oracles"]["tests"]["available"])
            self.assertTrue(cell["oracles"]["tests"]["passed"], cell["oracles"]["tests"])
            self.assertEqual(cell["candidate_modified_out_of_scope"], [])
            self.assertNotIn(
                rb.CANDIDATE_OUT_OF_SCOPE_NOTE, "; ".join(results["notes"]),
                "a clean run carried the out-of-scope note anyway",
            )

    def test_the_false_negative_is_labelled_everywhere_it_renders(self):
        """THE ACCEPTED COST, pinned as visible. This candidate genuinely makes the suite pass
        — by repairing behaviour in `alt.py`, which the reference patch never touched. The
        sweep reverts it and the cell reads `not solved`. That is a FALSE NEGATIVE, and the
        whole bargain is that a user can SEE it: on the cell, in the run's notes, in the
        measurement table, and as its own NOTE line in the verdict's per-candidate section.
        A visible false negative costs one investigation; an invisible false positive silently
        re-routes real work.
        """
        with tempfile.TemporaryDirectory() as td:
            results, run_dir = _run_general_harness_fixture(
                td, lambda cwd: (cwd / "alt.py").write_text('MODE = "PATCHED"\n')
            )
            cell = next(c for c in results["cells"] if not c["skipped"])
            self.assertFalse(cell["oracles"]["tests"]["passed"])
            self.assertEqual(cell["candidate_modified_out_of_scope"], ["alt.py"])
            self.assertTrue(
                any("alt.py" in n and rb.CANDIDATE_OUT_OF_SCOPE_NOTE in n
                    for n in results["notes"]),
                results["notes"],
            )

            card = rb.build_verdict(run_dir, "both", None)
            row = next(
                r for r in card["measurements"] if r["task_id"] == cell["task_id"]
            )
            self.assertEqual(row["candidate_modified_out_of_scope"], ["alt.py"])
            summary = next(
                s for s in card["summaries"] if s["candidate"] == cell["model"]
            )
            self.assertEqual(summary["not_solved_with_out_of_scope"], [cell["task_id"]])
            self.assertEqual(summary["out_of_scope_n"], 1)

            markdown = rb.render_verdict_markdown(card)
            table = markdown.partition("## measurement")[2].partition("## per candidate")[0]
            self.assertIn("out-of-scope (excluded)", table)
            self.assertIn("alt.py", table)
            self.assertIn("FALSE NEGATIVE", markdown)

    def test_an_unappliable_in_scope_patch_declines_to_grade_rather_than_failing_the_cell(self):
        """The other degradation. If the in-scope slice will not apply to the reconstructed
        base state, grading an unpatched substrate would report `not solved` for a reason that
        has nothing to do with the candidate's work — so the oracle reports unavailable, and
        `passed` stays `None` rather than becoming a `False` nobody measured."""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            base = build_oracle_fixture_repo(repo)
            task = _oracle_task(base, mode="general")
            bogus = (
                "diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n"
                "@@ -40,3 +40,3 @@\n-nothing like this line exists\n+replacement\n"
            )
            calls = []
            result = rb.oracle_tests(
                task, bogus, "cmd", lambda cmd, cwd: calls.append(cwd) or (0, "OK"),
                td / "scratch", target_repo=repo,
            )
        self.assertFalse(result["available"])
        self.assertIsNone(result["passed"])
        self.assertIn(rb.SUBSTRATE_APPLY_FAILED_NOTE, result["notes"])
        self.assertEqual(calls, [], "the test command graded an unpatched substrate")


def _tree_bytes(root):
    """`relpath -> bytes` for every file under `root`, `.git` excluded.

    `.git` is excluded because the substrate's repository is created by us, from the substrate
    itself, and holds no candidate bytes — the invariant is about the WORKING TREE the test
    command sees.
    """
    root = Path(root)
    out = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] == ".git":
            continue
        if path.is_symlink():
            out[str(rel)] = ("symlink", os.readlink(path))
        elif path.is_file():
            out[str(rel)] = ("file", path.read_bytes())
    return out


# ---------------------------------------------------------------------------------------------
# T17 — `--setup-cmd` stubs. NOTHING HERE IS A REAL INSTALLER: `npm`, `pip` and the network are
# never invoked, exactly as `--test-cmd` is never a real test suite in this file. The setup
# command rides the SAME injectable `test_runner` seam, so one stub serves both.

#: The literal handed to `--setup-cmd` in every test below. Deliberately not a real command name.
STUB_SETUP_CMD = "stub-setup"

#: What the stub "installs" — a path the base tree does not contain, which is what makes it an
#: ARTIFACT rather than source.
SETUP_ARTIFACT = "vendor/installed.txt"
SETUP_ARTIFACT_BODY = "stub dependencies installed\n"

#: The path the capture actually RECORDS: `_setup_artifact_paths` collapses a directory that did
#: not exist before setup into itself (so a lockfile install yields one `node_modules` entry,
#: not thirty thousand). The content hash of that entry is its whole manifest, so an edit
#: anywhere beneath it is caught under this name.
SETUP_ARTIFACT_ROOT = "vendor"


def _stub_setup(inner=None, *, fail=False, log=None, delay=0.0):
    """ONE stub runner for BOTH seams: `--setup-cmd` and `--test-cmd` share `test_runner`.

    Recognises `STUB_SETUP_CMD` and writes/fails accordingly, and delegates everything else to
    `inner` (the test command's own stub). `log`, when given, records every cwd setup ran in —
    which is how the tests prove setup ran once per TEMPLATE and never inside a candidate's
    sandbox.
    """
    def runner(cmd, cwd):
        if cmd == STUB_SETUP_CMD:
            if log is not None:
                log.append(str(cwd))
            if delay:
                time.sleep(delay)
            if fail:
                return 7, "stub setup failed: this sandbox has no network"
            target = Path(cwd) / SETUP_ARTIFACT
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(SETUP_ARTIFACT_BODY)
            return 0, "stub setup installed 1 dependency"
        if inner is None:
            return 0, "OK"
        return inner(cmd, cwd)
    return runner


def _reads_as(path):
    """A file's text, or None when it is binary/unreadable — for sweeps that hunt content."""
    try:
        return Path(path).read_text()
    except (UnicodeDecodeError, OSError):
        return None


def _needs_setup_test_runner(cmd, cwd):
    """A target whose tests CANNOT run until its dependencies are installed — the whole reason
    `--setup-cmd` exists. Absent the artifact it fails for a reason that has nothing to do with
    any candidate's work; present, it grades exactly like `_harness_test_runner`."""
    if not (Path(cwd) / SETUP_ARTIFACT).exists():
        return 3, "FAIL: dependencies are not installed (run the setup command first)"
    return _harness_test_runner(cmd, cwd)


def build_two_fix_repo(root):
    """Two issue-fix commits at DIFFERENT base commits, each touching a test file — so a run
    mines TWO objectively-scorable tasks. F1/F2/F3 all need more than one task with a template
    in play before they can manifest at all."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    (root / "alpha.py").write_text("VALUE = 1\n")
    (root / "beta.py").write_text("VALUE = 1\n")
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_alpha.py").write_text("# the base test surface\n")
    (tests / "test_beta.py").write_text("# the base test surface\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "c0: two modules and their tests")

    (root / "alpha.py").write_text("VALUE = 2\n")
    (tests / "test_alpha.py").write_text("EXPECT alpha == 2\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixes #1: alpha should be 2")

    (root / "beta.py").write_text("VALUE = 2\n")
    (tests / "test_beta.py").write_text("EXPECT beta == 2\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixes #2: beta should be 2")
    return _git(root, "rev-parse", "HEAD").strip()


def _two_fix_test_runner(cmd, cwd):
    """`build_two_fix_repo`'s stub suite: needs the install, then reads whatever withheld blob
    it was handed (`EXPECT <module> == <n>`) against that module's source."""
    cwd = Path(cwd)
    if not (cwd / SETUP_ARTIFACT).exists():
        return 3, "FAIL: dependencies are not installed (run the setup command first)"
    for test in sorted((cwd / "tests").glob("test_*.py")):
        text = test.read_text().strip()
        if not text.startswith("EXPECT"):
            continue
        _kw, module, _eq, want = text.split()[:4]
        source = cwd / f"{module}.py"
        if not source.exists() or f"VALUE = {want}" not in source.read_text():
            return 1, f"FAIL: {module}.VALUE is not {want}"
    return 0, "OK"


def _run_setup_fixture(td, mutate, *, models="haiku", setup_cmd=STUB_SETUP_CMD,
                       setup_keys=(), fail=False, log=None, delay=0.0, keep_work=False,
                       test_runner=None):
    """One stubbed general-mode run over `build_harness_fixture_repo`, with `--setup-cmd`
    wired through the same seam `--test-cmd` uses -> (results, run_dir)."""
    td = Path(td)
    repo = td / "target"
    build_harness_fixture_repo(repo)
    store = td / "store"
    argv = [
        "run", "--repo", str(repo), "--models", models, "--mode", "general",
        "--test-cmd", "setup-tests", "--store-dir", str(store),
        "--live", "--max-usd", "1000000",
    ]
    if setup_cmd:
        argv += ["--setup-cmd", setup_cmd]
    for key in setup_keys:
        argv += ["--setup-key", key]
    if keep_work:
        argv.append("--keep-work")
    args = rb.build_parser().parse_args(argv)
    inner = test_runner or _needs_setup_test_runner
    runner = _stub_setup(inner=inner, fail=fail, log=log, delay=delay) if setup_cmd else inner
    with contextlib.redirect_stdout(io.StringIO()):
        rb.cmd_run(args, runner=_candidate_that(mutate), test_runner=runner)
    run_dir = Path(rb.list_runs(store)[0][0]["path"])
    return json.loads((run_dir / "results.json").read_text()), run_dir


def _fix_calc(cwd):
    """A GENUINE in-scope repair: the mutated file is the reference patch's whole scope."""
    calc = Path(cwd) / "calc.py"
    calc.write_text(calc.read_text().replace("x > 10", "x >= 10"))


#: The adversarial surface F1 is about: every one of these is a file a real `--test-cmd` can
#: depend on, and every one of them returns False from `_matches_test_pattern`. A blacklist
#: has to name them; a whitelist never has to know they exist. `sitecustomize.py` is in the
#: list because Python imports it automatically at interpreter start — the purest example of
#: "the oracle is whatever runs, not whatever is named". `SETUP_ARTIFACT` joined the list with
#: T17: a prepared template is a NEW input to the grade substrate, so "write into the place the
#: setup step installs to" is a new shape of the same forgery.
ADVERSARIAL_PLANTS = (
    ("test-cmd entry point", "run_tests.py"),
    ("conftest", "conftest.py"),
    ("Makefile", "Makefile"),
    ("tox.ini", "tox.ini"),
    ("pytest.ini", "pytest.ini"),
    ("setup.py", "setup.py"),
    ("pyproject.toml", "pyproject.toml"),
    ("root sitecustomize", "sitecustomize.py"),
    ("brand-new file", "totally_new_module.py"),
    ("dotfile", ".env"),
    ("nested new file", "pkg/helpers/injected.py"),
    ("setup artifact path", SETUP_ARTIFACT),
)

FORGERY_MARKER = "REPO_BENCH_FORGED"


def _marker_sensitive_test_runner(cmd, cwd):
    """STUB `test_runner`: GREEN if the forgery marker is anywhere in the tree it is handed.

    Deliberately blind to WHICH file carries it — the point is that the substrate never
    contains the marker at all, whatever the candidate named the file. Falls through to
    grading the real injected bug, so mining's red-validation still works.
    """
    cwd = Path(cwd)
    for path in sorted(cwd.rglob("*")):
        rel = path.relative_to(cwd)
        if rel.parts and rel.parts[0] == ".git":
            continue
        if not path.is_file():
            continue
        try:
            if FORGERY_MARKER in path.read_text():
                return 0, f"OK (forged via {rel})"
        except (UnicodeDecodeError, OSError):
            continue
    calc = cwd / "calc.py"
    if not calc.exists():
        return 1, "FAIL: calc.py is missing"
    return (
        (1, "FAIL: classify(10) is no longer big") if "x > 10" in calc.read_text()
        else (0, "OK")
    )


class GradeSubstrateInvariantTests(unittest.TestCase):
    """T12R/F1 — PROVE THE CONSTRUCTION, NOT THE OUTCOMES.

        the grade result is a function of
            (the task's base state, the candidate's IN-SCOPE patch, the reference test blobs)
        and nothing else.

    A case test shows one hole is closed; the property test below shows the CLASS is, because
    it pins what the substrate IS rather than what some particular forgery fails to do.
    """

    def test_the_substrate_is_byte_identical_to_the_constructed_triple(self):
        """Built independently, from whole files rather than from patch application, so the
        assertion is not a restatement of `build_grade_substrate`'s own algorithm: take the
        base tree, overwrite exactly the IN-SCOPE paths with the candidate's own final content,
        write the blobs, and demand byte-identity in both directions."""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            base = build_harness_fixture_repo(repo)
            blobs = {"tests/test_extra.py": "assert True  # the withheld blob\n"}
            task = _oracle_task(base, mode="general", blobs=blobs, scope_path="calc.py")

            def mutate(cwd):
                # in scope: the reference patch touches calc.py
                (cwd / "calc.py").write_text("def classify(x):\n    return 'rewritten'\n")
                # everything below is OUT of scope, in every shape available
                (cwd / "run_tests.py").write_text(f"# {FORGERY_MARKER}\n")   # modified
                (cwd / "conftest.py").write_text(f"# {FORGERY_MARKER}\n")    # created
                (cwd / ".env").write_text(f"{FORGERY_MARKER}=1\n")           # dotfile
                (cwd / "alt.py").unlink()                                    # deleted
                (cwd / "pkg").mkdir()
                (cwd / "pkg" / "new.py").write_text(f"# {FORGERY_MARKER}\n")  # nested new

            patch, sandbox = _candidate_patch_for(repo, base, mutate, td / "cand")

            built = rb.build_grade_substrate(
                task, patch, td / "substrate", repo,
            )
            self.assertTrue(built["in_scope_applied"], built["notes"])

            # --- the independent construction -------------------------------------------
            expected_info = rb.make_sandbox(repo, base, td / "expected")
            expected = Path(expected_info["path"])
            scope = rb._reference_scope_paths(task["reference_patch"])
            self.assertEqual(scope, {"calc.py"}, "the fixture's whitelist is not what we think")
            for rel in sorted(scope):
                src, dst = sandbox / rel, expected / rel
                if src.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_bytes(src.read_bytes())
                elif dst.exists():
                    dst.unlink()
            for rel, blob in blobs.items():
                target = expected / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(blob)

            self.assertEqual(
                _tree_bytes(built["path"]), _tree_bytes(expected),
                "the grade substrate is NOT (base state + in-scope patch + test blobs)",
            )

            # …and, stated as its own claim so a reader does not have to derive it from the
            # dict comparison: not one out-of-scope artefact is present.
            substrate_files = _tree_bytes(built["path"])
            self.assertNotIn("conftest.py", substrate_files)
            self.assertNotIn(".env", substrate_files)
            self.assertNotIn("pkg/new.py", substrate_files)
            self.assertIn("alt.py", substrate_files)  # the deletion was never applied
            self.assertNotIn(
                FORGERY_MARKER,
                "".join(
                    value.decode("utf-8", "replace")
                    for kind, value in substrate_files.values() if kind == "file"
                ),
            )

    def test_a_templated_substrate_is_byte_identical_to_the_constructed_triple(self):
        """T17 — THE SAME PROPERTY, WITH A PREPARED TEMPLATE IN PLAY.

        A `--setup-cmd` template is a NEW input to the grade substrate, so the invariant has to
        be re-proved rather than assumed to survive:

            grade substrate = (pristine base state + setup artifacts)
                              + the candidate's IN-SCOPE patch + the reference test blobs
            and nothing else.

        The expected tree is built INDEPENDENTLY again — a fresh base sandbox, the mined
        mutation applied with a plain `git apply`, the same setup stub run in it directly, the
        in-scope paths overwritten from the candidate's own final content, blobs last — so this
        is not a restatement of the engine's algorithm.

        T17R/F5: the task is a REAL MINED GENERAL-MODE TASK, carrying a non-None `setup_patch`.
        The previous version used `_oracle_task`, which pins `setup_patch: None` even for
        `mode="general"` — so the property was proved on the one shape where the interaction
        between the injected bug and the template cannot arise, which is exactly where the
        template machinery is most load-bearing.
        """
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            base = build_harness_fixture_repo(repo)
            mined, _notes = rb.mine_general_tasks(
                repo, base, limit=1, test_cmd="harness-tests",
                test_runner=_harness_test_runner, scratch_dir=td / "mining",
            )
            self.assertEqual(len(mined), 1, "the general miner produced no task to prove on")
            task = mined[0]
            self.assertTrue(
                task["setup_patch"], "the mined task carries no injected bug (F5's whole point)"
            )
            blobs = {"tests/test_extra.py": "assert True  # the withheld blob\n"}
            task["test_blobs"] = dict(blobs)

            def mutate(cwd):
                (cwd / "calc.py").write_text("def classify(x):\n    return 'rewritten'\n")
                (cwd / "run_tests.py").write_text(f"# {FORGERY_MARKER}\n")
                (cwd / "conftest.py").write_text(f"# {FORGERY_MARKER}\n")
                (cwd / ".env").write_text(f"{FORGERY_MARKER}=1\n")
                (cwd / "alt.py").unlink()
                # …and the shape only a template makes available: write into the very path the
                # setup step installs to, hoping the overlay will carry it into the substrate.
                artifact = cwd / SETUP_ARTIFACT
                artifact.parent.mkdir(parents=True, exist_ok=True)
                artifact.write_text(f"# {FORGERY_MARKER}\n")

            # The candidate's own sandbox carries the injected bug, exactly as `cmd_run` builds
            # it — a general-mode candidate patch captured off the pristine base would be a
            # different (and easier) input than the one the engine really gets.
            cand_info, _baseline = rb.prepare_cell_sandbox(task, repo, td / "cand")
            sandbox = Path(cand_info["path"])
            mutate(sandbox)
            patch = rb.capture_patch(sandbox)

            setup_log = []
            templates = rb.GradeTemplates(
                repo, td / "templates", STUB_SETUP_CMD, test_runner=_stub_setup(log=setup_log),
            )
            self.addCleanup(templates.cleanup)
            built = rb.build_grade_substrate(
                task, patch, td / "substrate", repo, templates=templates,
            )
            self.assertTrue(built["in_scope_applied"], built["notes"])

            # --- the independent construction -------------------------------------------
            expected_info = rb.make_sandbox(repo, base, td / "expected")
            expected = Path(expected_info["path"])
            setup_patch_file = td / "independent.patch"
            setup_patch_file.write_text(task["setup_patch"])
            _git(expected, "apply", str(setup_patch_file))
            _stub_setup()(STUB_SETUP_CMD, str(expected))
            scope = rb._reference_scope_paths(task["reference_patch"])
            self.assertEqual(scope, {"calc.py"}, "the fixture's whitelist is not what we think")
            for rel in sorted(scope):
                src, dst = sandbox / rel, expected / rel
                if src.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_bytes(src.read_bytes())
                elif dst.exists():
                    dst.unlink()
            for rel, blob in blobs.items():
                target = expected / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(blob)

            substrate_files = _tree_bytes(built["path"])
            self.assertEqual(
                substrate_files, _tree_bytes(expected),
                "the templated grade substrate is NOT (base state + setup artifacts + in-scope "
                "patch + test blobs)",
            )

            # The setup really happened — otherwise byte-identity would be trivially true of
            # two trees that were both never set up.
            self.assertIn(SETUP_ARTIFACT, substrate_files)
            self.assertEqual(
                substrate_files[SETUP_ARTIFACT], ("file", SETUP_ARTIFACT_BODY.encode()),
                "the candidate's plant reached the substrate through the setup artifact path",
            )
            self.assertNotIn(
                FORGERY_MARKER,
                "".join(
                    value.decode("utf-8", "replace")
                    for kind, value in substrate_files.values() if kind == "file"
                ),
            )

            # THE TEMPLATE WAS NEVER BUILT FROM, OR CONTAMINATED BY, A CANDIDATE'S TREE. The
            # captured artifacts live OUTSIDE the run dir now (T17R/F1), so that is where the
            # claim has to be checked — and the build area under the run dir must hold nothing.
            self.assertEqual(len(setup_log), 1, "setup ran more than once for one template")
            self.assertNotIn(str(sandbox), setup_log)
            for cwd in setup_log:
                self.assertTrue(
                    Path(cwd).is_relative_to(td / "templates"),
                    f"setup ran outside the template area: {cwd}",
                )
            store_tree = _tree_bytes(templates.store_root())
            self.assertTrue(store_tree, "no template artefacts were captured at all")
            self.assertNotIn(
                FORGERY_MARKER,
                "".join(
                    value.decode("utf-8", "replace")
                    for kind, value in store_tree.values() if kind == "file"
                ),
                "a candidate's bytes reached the template",
            )
            self.assertEqual(
                _tree_bytes(td / "templates"), {},
                "the build area kept a copy of the artifacts inside the run dir's working area",
            )

    def test_the_out_of_scope_split_reaches_the_report_and_not_the_substrate(self):
        """The two halves of `_split_patch_by_scope` must not drift: what is reported is
        evidence, what is applied is the guarantee, and they are different things."""
        scope = {"in.py"}
        patch = (
            "--- a/in.py\n+++ b/in.py\n@@ -1 +1 @@\n-a\n+b\n"
            "--- a/out.py\n+++ b/out.py\n@@ -1 +1 @@\n-c\n+d\n"
        )
        in_scope, out_of_scope = rb._split_patch_by_scope(patch, scope)
        self.assertIn("in.py", in_scope)
        self.assertNotIn("out.py", in_scope)
        self.assertEqual(out_of_scope, ["out.py"])

    def test_no_candidate_patch_at_all_still_builds_the_base_state(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            base = build_harness_fixture_repo(repo)
            task = _oracle_task(base, mode="general", scope_path="calc.py")
            built = rb.build_grade_substrate(task, "", td / "substrate", repo)
            self.assertTrue(built["in_scope_applied"])
            self.assertEqual(built["out_of_scope"], [])
            self.assertIn("calc.py", _tree_bytes(built["path"]))


class AdversarialPlantTests(unittest.TestCase):
    """T12R/F1 — the parameterized proof. Every plant below is a file a real `--test-cmd` can
    depend on and that `_matches_test_pattern` returns False for; the stub runner goes GREEN
    the moment the marker appears ANYWHERE in the tree it is handed. None of them can change
    the grade, and none of them had to be anticipated by the engine — the substrate simply
    never contains anything the reference patch did not put in scope."""

    def test_no_plant_outside_the_reference_scope_can_change_the_grade(self):
        for label, rel_path in ADVERSARIAL_PLANTS:
            with self.subTest(plant=label, path=rel_path):
                with self.assertRaises(AssertionError):
                    # sanity: the plant really is outside the test-pattern net, so a
                    # name-based fix would NOT have caught it
                    self.assertTrue(
                        rb._matches_test_pattern(rel_path, rb.DEFAULT_TEST_PATTERNS)
                    )

                def mutate(cwd, rel_path=rel_path):
                    target = Path(cwd) / rel_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(f"# {FORGERY_MARKER}\n")

                with tempfile.TemporaryDirectory() as td:
                    td = Path(td)
                    repo = td / "target"
                    build_harness_fixture_repo(repo)
                    store = td / "store"
                    args = rb.build_parser().parse_args([
                        "run", "--repo", str(repo), "--models", "haiku", "--mode", "general",
                        "--test-cmd", "marker-tests", "--store-dir", str(store),
                        "--live", "--max-usd", "1000000", "--keep-work",
                    ])
                    with contextlib.redirect_stdout(io.StringIO()):
                        rb.cmd_run(
                            args, runner=_candidate_that(mutate),
                            test_runner=_marker_sensitive_test_runner,
                        )
                    run_dir = Path(rb.list_runs(store)[0][0]["path"])
                    results = json.loads((run_dir / "results.json").read_text())
                    cell = next(c for c in results["cells"] if not c["skipped"])

                    # The forgery is REAL: the candidate's own tree grades green.
                    sandbox = next(
                        p for p in (run_dir / "work").iterdir()
                        if p.is_dir() and p.name.startswith("cell-")
                    )
                    self.assertEqual(
                        _marker_sensitive_test_runner("marker-tests", str(sandbox))[0], 0,
                        f"{label}: the plant does not actually forge anything",
                    )
                    self.assertTrue(cell["oracles"]["tests"]["available"])
                    self.assertFalse(
                        cell["oracles"]["tests"]["passed"],
                        f"{label} ({rel_path}) forged a `solved`",
                    )

    def test_no_plant_reaches_a_TEMPLATED_substrate_either(self):
        """T17 — the same sweep, with a prepared `--setup-cmd` template feeding the substrate.

        A template is a new input to the grading substrate, and a new input is exactly how the
        four earlier leaks in this kit got in. So the sweep is re-run rather than the property
        assumed to carry over: every plant still fails, for the same structural reason (it was
        never in scope, so it was never applied) and not because anything here anticipated it.
        """
        for label, rel_path in ADVERSARIAL_PLANTS:
            with self.subTest(plant=label, path=rel_path):
                def mutate(cwd, rel_path=rel_path):
                    target = Path(cwd) / rel_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(f"# {FORGERY_MARKER}\n")

                with tempfile.TemporaryDirectory() as td:
                    td = Path(td)
                    repo = td / "target"
                    build_harness_fixture_repo(repo)
                    store = td / "store"
                    args = rb.build_parser().parse_args([
                        "run", "--repo", str(repo), "--models", "haiku", "--mode", "general",
                        "--test-cmd", "marker-tests", "--setup-cmd", STUB_SETUP_CMD,
                        "--store-dir", str(store),
                        "--live", "--max-usd", "1000000", "--keep-work",
                    ])
                    with contextlib.redirect_stdout(io.StringIO()):
                        rb.cmd_run(
                            args, runner=_candidate_that(mutate),
                            test_runner=_stub_setup(inner=_marker_sensitive_test_runner),
                        )
                    run_dir = Path(rb.list_runs(store)[0][0]["path"])
                    results = json.loads((run_dir / "results.json").read_text())
                    cell = next(c for c in results["cells"] if not c["skipped"])

                    # The template really was in play — otherwise this re-run proves nothing.
                    self.assertEqual(results["setup"]["templates_prepared"], 1)
                    self.assertGreaterEqual(results["setup"]["gradings_served"], 1)

                    sandbox = next(
                        p for p in (run_dir / "work").iterdir()
                        if p.is_dir() and p.name.startswith("cell-")
                    )
                    self.assertEqual(
                        _marker_sensitive_test_runner("marker-tests", str(sandbox))[0], 0,
                        f"{label}: the plant does not actually forge anything",
                    )
                    self.assertTrue(cell["oracles"]["tests"]["available"])
                    self.assertFalse(
                        cell["oracles"]["tests"]["passed"],
                        f"{label} ({rel_path}) forged a `solved` through a templated substrate",
                    )


class ReferenceScopeTests(unittest.TestCase):
    """`_reference_scope_paths` defines what a candidate may legitimately change. Generous on
    purpose (both sides of a rename, both sides of a delete/add): every path it admits comes
    from an artifact mined out of the target's history, which no candidate can write, so
    breadth here only reduces false negatives."""

    def test_both_diff_header_sides_are_in_scope(self):
        patch = (
            "diff --git a/src/m.py b/src/m.py\n"
            "--- a/src/m.py\n+++ b/src/m.py\n@@ -1 +1 @@\n-a\n+b\n"
        )
        self.assertEqual(rb._reference_scope_paths(patch), {"src/m.py"})

    def test_a_deletion_resolves_from_the_minus_side(self):
        patch = "diff --git a/gone.py b/gone.py\n--- a/gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n"
        self.assertEqual(rb._reference_scope_paths(patch), {"gone.py"})

    def test_a_rename_puts_both_names_in_scope(self):
        patch = (
            "diff --git a/old.py b/new.py\nsimilarity index 100%\n"
            "rename from old.py\nrename to new.py\n"
        )
        self.assertEqual(rb._reference_scope_paths(patch), {"old.py", "new.py"})

    def test_an_empty_reference_scopes_nothing(self):
        self.assertEqual(rb._reference_scope_paths(""), set())
        self.assertEqual(rb._reference_scope_paths(None), set())

    def test_test_hunks_stay_in_scope(self):
        """Deliberately NOT stripped here: a file the FIX commit touched is legitimately in
        play for the candidate too. The separate test-surface restore is what keeps those
        from being forgeable — this function is about SCOPE, not about trust."""
        patch = (
            "--- a/m.py\n+++ b/m.py\n@@ -1 +1 @@\n-a\n+b\n"
            "--- a/tests/test_m.py\n+++ b/tests/test_m.py\n@@ -0,0 +1 @@\n+assert True\n"
        )
        self.assertEqual(rb._reference_scope_paths(patch), {"m.py", "tests/test_m.py"})


class ApplyNullClobberTests(unittest.TestCase):
    """F3 (Phase 4 review) — `apply` wrote an all-`None` tier map over a good one and reported
    success. Engine-producible, not hand-edit-only: `verdict --goal daily-driver` emits
    `tier_map: None`, and `_daily_driver` legitimately returns `pick: None` when no candidate
    is eligible-and-priced."""

    def _seed_prefs(self, prefs_path):
        prefs_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": rb.PREFS_SCHEMA_VERSION,
            "applied_at": "2026-01-01T00:00:00+00:00",
            "source_run": "2026-01-01-aaaa",
            "repo": "/some/target",
            "tiers": {"strong": "fake-gamma-1", "mid": "fake-beta-1", "weak": "fake-alpha-1"},
            "daily_driver": "fake-alpha-1",
            "labels": [],
        }
        prefs_path.write_text(json.dumps(payload, indent=2) + "\n")
        return payload

    def test_a_payload_naming_no_model_refuses_and_leaves_the_good_file(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs" / "repo-bench.json"
            good = self._seed_prefs(prefs_path)
            _run_id, run_dir = _write_run_with_verdict(
                store,
                tier_slots={"strong": None, "mid": None, "weak": None},
                daily_driver_pick=None,
                candidates=["fake-alpha-1"],
            )
            with self.assertRaises(ValueError) as ctx:
                rb.apply_verdict(run_dir, prefs_path, FAKE_PRICING)
            self.assertIn("names no model", str(ctx.exception))
            self.assertEqual(
                json.loads(prefs_path.read_text()), good,
                "an empty verdict erased a good prefs file",
            )

    def test_a_payload_naming_no_model_refuses_even_with_no_prior_file(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            _run_id, run_dir = _write_run_with_verdict(
                store,
                tier_slots={"strong": None, "mid": None, "weak": None},
                daily_driver_pick=None,
                candidates=["fake-alpha-1"],
            )
            with self.assertRaises(ValueError):
                rb.apply_verdict(run_dir, prefs_path, FAKE_PRICING)
            self.assertFalse(prefs_path.exists())

    def test_a_goal_scoped_verdict_never_clears_slots_it_never_measured(self):
        """`--goal daily-driver` emits `tier_map: None` — absent because the GOAL excluded it,
        not because the run measured nothing there. Applying it over a populated file used to
        blank all three tiers at exit 0."""
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            good = self._seed_prefs(prefs_path)
            verdict = {
                "verdict_schema_version": rb.VERDICT_SCHEMA_VERSION,
                "goal": "daily-driver",
                "min_tasks": rb.MIN_EVIDENCE_TASKS,
                "below_floor": False,
                "below_floor_label": None,
                "rule": "synthetic rule text",
                "capability_order": [],
                "tier_map": None,
                "daily_driver": {"pick": "fake-beta-1", "notes": []},
                "three_legs": [], "disagreements": [], "labels": [], "notes": [],
            }
            _run_id, run_dir = _write_run_with_raw_verdict(store, verdict)
            with self.assertRaises(ValueError) as ctx:
                rb.apply_verdict(run_dir, prefs_path, FAKE_PRICING)
            self.assertIn("tiers", str(ctx.exception))
            self.assertIn("--goal both", str(ctx.exception))
            self.assertEqual(json.loads(prefs_path.read_text()), good)

    def test_a_goal_scoped_verdict_applies_when_there_is_nothing_to_clear(self):
        """The refusal is about DESTROYING state, not about goal-scoping itself: with no prior
        file (or no value in the unmeasured slot) the same card applies cleanly."""
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            verdict = {
                "verdict_schema_version": rb.VERDICT_SCHEMA_VERSION,
                "goal": "daily-driver",
                "min_tasks": rb.MIN_EVIDENCE_TASKS,
                "below_floor": False,
                "below_floor_label": None,
                "rule": "synthetic rule text",
                "capability_order": [],
                "tier_map": None,
                "daily_driver": {"pick": "fake-beta-1", "notes": []},
                "three_legs": [], "disagreements": [], "labels": [], "notes": [],
            }
            _run_id, run_dir = _write_run_with_raw_verdict(store, verdict)
            payload, old = rb.apply_verdict(run_dir, prefs_path, FAKE_PRICING)
            self.assertIsNone(old)
            self.assertEqual(payload["daily_driver"], "fake-beta-1")
            self.assertEqual(
                payload["tiers"], {"strong": None, "mid": None, "weak": None}
            )

    def test_a_non_string_slot_value_refuses_with_a_sentence_not_a_traceback(self):
        """It used to raise AttributeError out of `cost_report.match_model` — a type `main`
        does not handle, so `apply` printed a traceback where every sibling refusal prints one
        plain line."""
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            verdict = {
                "verdict_schema_version": rb.VERDICT_SCHEMA_VERSION,
                "goal": "both",
                "min_tasks": rb.MIN_EVIDENCE_TASKS,
                "below_floor": False,
                "below_floor_label": None,
                "rule": "synthetic rule text",
                "capability_order": [],
                "tier_map": {
                    "slots": {"strong": 123, "mid": None, "weak": None},
                    "nearest_neighbors": {}, "role_gloss": {}, "notes": [],
                },
                "daily_driver": {"pick": None, "notes": []},
                "three_legs": [], "disagreements": [], "labels": [], "notes": [],
            }
            run_id, _run_dir = _write_run_with_raw_verdict(store, verdict)
            err = io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
                rb.main([
                    "apply", "--run", run_id, "--store-dir", str(store),
                    "--prefs-path", str(prefs_path),
                ])
            self.assertEqual(ctx.exception.code, 2)
            self.assertIn("not a model id", err.getvalue())
            self.assertNotIn("Traceback", err.getvalue())
            self.assertFalse(prefs_path.exists())

    def test_a_non_string_daily_driver_pick_refuses_the_same_way(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            prefs_path = Path(td) / "prefs.json"
            verdict = {
                "verdict_schema_version": rb.VERDICT_SCHEMA_VERSION,
                "goal": "both",
                "min_tasks": rb.MIN_EVIDENCE_TASKS,
                "below_floor": False,
                "below_floor_label": None,
                "rule": "synthetic rule text",
                "capability_order": [],
                "tier_map": {
                    "slots": {"strong": None, "mid": None, "weak": None},
                    "nearest_neighbors": {}, "role_gloss": {}, "notes": [],
                },
                "daily_driver": {"pick": ["fake-alpha-1"], "notes": []},
                "three_legs": [], "disagreements": [], "labels": [], "notes": [],
            }
            _run_id, run_dir = _write_run_with_raw_verdict(store, verdict)
            with self.assertRaises(ValueError) as ctx:
                rb.apply_verdict(run_dir, prefs_path, FAKE_PRICING)
            self.assertIn("not a model id", str(ctx.exception))
            self.assertFalse(prefs_path.exists())


class VerdictJsonIsMachineReadableTests(unittest.TestCase):
    """F4 (Phase 4 review) — `verdict --json` printed a blank line and `verdict.md: <path>`
    AFTER the JSON body, so `json.loads` died with `Extra data` while `plan --json` and
    `list --json` both parsed."""

    def test_stdout_parses_and_the_receipt_goes_to_stderr(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            run_id, run_dir = _write_run(
                store, [_v_cell("t1", "fake-alpha-1", passed=True)]
            )
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = rb.main(["verdict", "--run", run_id, "--store-dir", str(store), "--json"])
            self.assertIsNone(rc)
            card = json.loads(out.getvalue())
            self.assertEqual(card["run_id"], run_id)
            self.assertNotIn("verdict.md:", out.getvalue())
            self.assertIn("verdict.md:", err.getvalue())
            self.assertTrue((run_dir / "verdict.md").exists())

    def test_the_human_path_still_prints_the_receipt_on_stdout(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            run_id, _run_dir = _write_run(
                store, [_v_cell("t1", "fake-alpha-1", passed=True)]
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rb.main(["verdict", "--run", run_id, "--store-dir", str(store)])
            self.assertIn("verdict.md:", out.getvalue())


class GeneralMiningShortfallNoteTests(unittest.TestCase):
    """F9 (Phase 4 review) — asking for 3 tasks and getting 1 said nothing at all unless the
    examine bound had been hit. Exhaustive-but-short is a different fact from truncated-scan,
    and both deserve to be stated."""

    def test_a_short_exhaustive_scan_is_noted_without_claiming_partial_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            head = build_harness_fixture_repo(repo)
            tasks, notes = rb.mine_general_tasks(
                repo, head, limit=3, test_cmd="harness-tests",
                test_runner=_harness_test_runner, scratch_dir=td / "scratch",
            )
            self.assertEqual(len(tasks), 1, [t["task_id"] for t in tasks])
            joined = " | ".join(notes)
            self.assertIn("mined 1/3 requested task(s)", joined)
            self.assertIn("scanned exhaustively", joined)
            self.assertNotIn(
                "partial coverage", joined,
                "an exhaustive scan claimed partial coverage — the two facts got merged",
            )

    def test_a_full_yield_carries_no_shortfall_note(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            head = build_harness_fixture_repo(repo)
            tasks, notes = rb.mine_general_tasks(
                repo, head, limit=1, test_cmd="harness-tests",
                test_runner=_harness_test_runner, scratch_dir=td / "scratch",
            )
            self.assertEqual(len(tasks), 1)
            self.assertNotIn("requested task(s)", " | ".join(notes))


class DemoExercisesBothModesTests(unittest.TestCase):
    """F2 (Phase 4 review) — PLAN's Done-means clause 1 says the demo exercises BOTH
    acquisition modes and the skill told users so, while `cmd_demo` hardcoded
    `--mode issue-replay`. The capability was real and unit-tested; only its own acceptance
    surface omitted it."""

    def test_the_demo_runs_general_mode_and_shows_the_harness_forgery_failing(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = rb.cmd_demo(rb.build_parser().parse_args(["demo"]))
        self.assertEqual(rc, 0)
        text = out.getvalue()
        self.assertIn("GENERAL (mutation-repair) mode", text)
        self.assertIn("mode=general", text)
        self.assertIn("run_tests.py", text)
        self.assertIn("tests.passed=False", text)
        self.assertIn("no model dispatched", text)

    def test_the_demo_exercises_setup_cmd_and_both_of_its_leak_mechanisms(self):
        """T17R/F9 — `--setup-cmd` is a new INPUT to the grade substrate, and the Done-means
        smoke never exercised it. The demo now runs a target that must install first, shows a
        candidate's sweep for the artifact store coming back empty, and shows the content-hash
        verification refusing a tampered store on its own."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = rb.cmd_demo(rb.build_parser().parse_args(["demo"]))
        self.assertEqual(rc, 0)
        text = out.getvalue()
        self.assertIn("--setup-cmd", text)
        self.assertIn("grade templates: 1 prepared", text)
        self.assertIn("swept ../ and ../../ of its own sandbox", text)
        self.assertIn("store_under_run_dir=False", text)
        self.assertIn("available=False passed=None", text)
        # …and what it ran was the stub, never a real installer: the demo's setup command is a
        # made-up name and its whole "install" is one file written by an injected runner.
        self.assertEqual(rb.DEMO_SETUP_CMD, "demo-setup")


def build_deps_fixture_repo(root):
    """Three commits: a dependency manifest that is IDENTICAL across the first two and changes
    at the third. `--setup-key` keys templates on that manifest's content, so c1 and c2 must
    collapse to one template and c3 must not. Returns (c1, c2, c3)."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    (root / "deps.txt").write_text("libfoo==1.0\n")
    (root / "app.py").write_text("VALUE = 1\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "c1: app + deps")
    c1 = _git(root, "rev-parse", "HEAD").strip()

    (root / "app.py").write_text("VALUE = 2\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "c2: app changes, deps do not")
    c2 = _git(root, "rev-parse", "HEAD").strip()

    (root / "deps.txt").write_text("libfoo==2.0\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "c3: deps change")
    c3 = _git(root, "rev-parse", "HEAD").strip()
    return c1, c2, c3


def _deps_task(task_id, base_commit):
    return {"task_id": task_id, "mode": "issue-replay", "base_commit": base_commit,
            "setup_patch": None}


class SetupCmdFlagTests(unittest.TestCase):
    """T17 — the flag surface. `--setup-cmd` is opt-in, never invented, and shared by `plan`
    and `run` because `run` re-prints `plan`'s card on its refusal paths."""

    def test_both_subcommands_accept_setup_cmd_and_repeatable_setup_key(self):
        for command in ("plan", "run"):
            with self.subTest(command=command):
                args = rb.build_parser().parse_args([
                    command, "--repo", ".", "--models", "haiku",
                    "--setup-cmd", STUB_SETUP_CMD,
                    "--setup-key", "package-lock.json", "--setup-key", "pnpm-lock.yaml",
                ])
                self.assertEqual(args.setup_cmd, STUB_SETUP_CMD)
                self.assertEqual(args.setup_key, ["package-lock.json", "pnpm-lock.yaml"])

    def test_the_default_is_no_setup_command_at_all(self):
        args = rb.build_parser().parse_args(["run", "--repo", ".", "--models", "haiku"])
        self.assertIsNone(args.setup_cmd)
        self.assertIsNone(args.setup_key)

    def test_plan_says_a_setup_command_is_configured_and_never_runs_it(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_harness_fixture_repo(repo)
            log = []
            card = rb.build_plan(
                target_repo=repo, models=["fake-haiku-1"], mode="general", limit=1,
                test_cmd="setup-tests", pricing=FIXTURE_PRICING, scratch_dir=td / "work",
                test_runner=_stub_setup(inner=_needs_setup_test_runner, log=log),
                setup_cmd=STUB_SETUP_CMD,
            )
        self.assertIn(rb.SETUP_PLAN_NOTE, card["notes"])
        self.assertEqual(log, [], "`plan` ran the setup command")

    def test_a_setup_cmd_without_a_test_cmd_says_it_will_do_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_harness_fixture_repo(repo)
            card = rb.build_plan(
                target_repo=repo, models=["fake-haiku-1"], mode="issue-replay", limit=1,
                pricing=FIXTURE_PRICING, scratch_dir=td / "work", setup_cmd=STUB_SETUP_CMD,
            )
        self.assertIn(rb.SETUP_WITHOUT_TEST_CMD_NOTE, card["notes"])

    def test_no_note_at_all_when_the_flag_is_absent(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_harness_fixture_repo(repo)
            card = rb.build_plan(
                target_repo=repo, models=["fake-haiku-1"], mode="issue-replay", limit=1,
                pricing=FIXTURE_PRICING, scratch_dir=td / "work",
            )
        for note in card["notes"]:
            self.assertNotIn("--setup-cmd", note)


class SetupCmdMakesInstallTargetsBenchmarkableTests(unittest.TestCase):
    """T17's acceptance: a target whose tests cannot run until something is installed."""

    def test_without_setup_a_genuine_fix_cannot_be_graded_green(self):
        """The premise, asserted rather than assumed — otherwise the test below proves
        nothing. The fixture's test command really does need the install."""
        with tempfile.TemporaryDirectory() as td:
            results, _run_dir = _run_setup_fixture(td, _fix_calc, setup_cmd=None)
        cell = next(c for c in results["cells"] if not c["skipped"])
        self.assertTrue(cell["oracles"]["tests"]["available"])
        self.assertFalse(
            cell["oracles"]["tests"]["passed"],
            "the fixture does not actually need a setup step",
        )
        self.assertNotIn("setup", results)

    def test_with_setup_the_same_genuine_fix_reads_solved(self):
        with tempfile.TemporaryDirectory() as td:
            results, _run_dir = _run_setup_fixture(td, _fix_calc)
        cell = next(c for c in results["cells"] if not c["skipped"])
        self.assertTrue(cell["oracles"]["tests"]["available"], cell["oracles"]["tests"])
        self.assertTrue(
            cell["oracles"]["tests"]["passed"],
            "a target with an install step still cannot be graded",
        )
        self.assertEqual(results["setup"]["templates_prepared"], 1)
        self.assertEqual(results["setup"]["templates_failed"], 0)

    def test_setup_is_never_run_inside_a_candidates_sandbox(self):
        log = []
        with tempfile.TemporaryDirectory() as td:
            _results, run_dir = _run_setup_fixture(td, _fix_calc, log=log, keep_work=True)
            self.assertTrue(log, "setup never ran at all")
            for cwd in log:
                self.assertIn(
                    "templates", Path(cwd).parts,
                    f"the setup command ran outside the template area: {cwd}",
                )
                self.assertFalse(
                    Path(cwd).name.startswith("cell-"),
                    f"the setup command ran in a candidate's sandbox: {cwd}",
                )
            cell_dirs = [
                p for p in (run_dir / "work").iterdir()
                if p.is_dir() and p.name.startswith("cell-")
            ]
            self.assertTrue(cell_dirs, "the fixture kept no candidate sandbox to check")
            for cell_dir in cell_dirs:
                self.assertFalse(
                    (cell_dir / SETUP_ARTIFACT).exists(),
                    "a candidate's sandbox carries setup artifacts",
                )


class SetupTemplateCachingTests(unittest.TestCase):
    """T17 item 2/3 — without caching this feature is worse than the problem it solves."""

    def test_setup_runs_once_per_template_not_once_per_grading(self):
        log = []
        with tempfile.TemporaryDirectory() as td:
            results, _run_dir = _run_setup_fixture(
                td, _fix_calc, models="haiku,sonnet", log=log
            )
        graded = [c for c in results["cells"] if not c["skipped"]]
        self.assertEqual(len(graded), 2, "the fixture did not grade two candidates")
        self.assertEqual(
            len(log), 1,
            f"setup ran {len(log)} time(s) for 1 template and {len(graded)} gradings",
        )
        self.assertEqual(results["setup"]["templates_prepared"], 1)
        self.assertEqual(results["setup"]["gradings_served"], len(graded))

    def test_setup_key_collapses_tasks_whose_keyed_content_matches(self):
        """The collapse survives T17R/F2's cross-base check — at the cost of ONE extra
        preparation for the whole run, not one per task. The stub install is reproducible, so
        the probe at the second base matches and every later task reuses the shared record."""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            c1, c2, c3 = build_deps_fixture_repo(repo)
            log = []
            templates = rb.GradeTemplates(
                repo, td / "templates", STUB_SETUP_CMD, test_runner=_stub_setup(log=log),
                key_paths=("deps.txt",),
            )
            self.addCleanup(templates.cleanup)
            first = templates.prepare(_deps_task("t1", c1))
            second = templates.prepare(_deps_task("t2", c2))
            third = templates.prepare(_deps_task("t3", c3))

            self.assertEqual(
                first["key"], second["key"],
                "two bases with identical deps.txt did not share a template",
            )
            self.assertTrue(
                first["share_verified"],
                "the shared template was reused without being verified across bases",
            )
            self.assertNotEqual(
                first["key"], third["key"],
                "a changed deps.txt still shared a template",
            )
            self.assertEqual(
                len(log), 3,
                "expected one install per distinct key plus ONE cross-base verification probe",
            )
            report = templates.report()
            self.assertEqual(report["templates_prepared"], 3)
            self.assertEqual(sorted(first["task_ids"]), ["t1", "t2"])
            self.assertEqual(report["setup_key_paths"], ["deps.txt"])
            self.assertEqual(
                [t["role"] for t in report["templates"]].count(rb.SHARING_PROBE_ROLE), 1,
                "the extra preparation is not reported as the verification probe it is",
            )
            self.assertTrue(
                any("sharing verified" in n for n in report["sharing_notes"]), report
            )

            # A THIRD task at yet another base reuses the verified record without probing again.
            fourth = templates.prepare(_deps_task("t4", c2))
            self.assertEqual(fourth["key"], first["key"])
            self.assertEqual(len(log), 3, "a verified template was probed a second time")

    def test_without_setup_key_every_distinct_base_gets_its_own_template(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            c1, c2, c3 = build_deps_fixture_repo(repo)
            log = []
            templates = rb.GradeTemplates(
                repo, td / "templates", STUB_SETUP_CMD, test_runner=_stub_setup(log=log),
            )
            self.addCleanup(templates.cleanup)
            keys = {
                templates.prepare(_deps_task(f"t{n}", commit))["key"]
                for n, commit in enumerate((c1, c2, c3), start=1)
            }
        self.assertEqual(len(keys), 3)
        self.assertEqual(len(log), 3)

    def test_the_key_basis_is_reported_rather_than_being_an_unaccountable_hash(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            c1, _c2, _c3 = build_deps_fixture_repo(repo)
            plain = rb.GradeTemplates(repo, td / "a", STUB_SETUP_CMD, test_runner=_stub_setup())
            keyed = rb.GradeTemplates(
                repo, td / "b", STUB_SETUP_CMD, test_runner=_stub_setup(),
                key_paths=("deps.txt",),
            )
            self.addCleanup(plain.cleanup)
            self.addCleanup(keyed.cleanup)
            self.assertEqual(plain.key_basis(_deps_task("t1", c1)), [f"base commit {c1}"])
            basis = keyed.key_basis(_deps_task("t1", c1))
            self.assertEqual(len(basis), 1)
            self.assertTrue(basis[0].startswith("--setup-key deps.txt @ "))

    def test_an_absent_setup_key_path_never_collapses_every_task_onto_one_template(self):
        """T17R/F7 — a typo'd `--setup-key` used to record `absent` for every task, keying them
        all identically: the maximum-amplitude form of the cross-task artifact defect, reachable
        by one misspelled flag. The base commit goes back into the basis and the run says so."""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            c1, c2, _c3 = build_deps_fixture_repo(repo)
            log = []
            templates = rb.GradeTemplates(
                repo, td / "templates", STUB_SETUP_CMD, test_runner=_stub_setup(log=log),
                key_paths=("package.lock",),  # never existed in this repo
            )
            self.addCleanup(templates.cleanup)
            first = templates.prepare(_deps_task("t1", c1))
            second = templates.prepare(_deps_task("t2", c2))
            self.assertNotEqual(
                first["key"], second["key"],
                "an absent --setup-key path collapsed two different bases onto one template",
            )
            report = templates.report()
            # One entry per (path, base commit): the label has to say WHERE the path was
            # missing, since a manifest added partway through a repo's history is absent at some
            # bases and present at others.
            self.assertEqual({e["path"] for e in report["key_paths_absent"]}, {"package.lock"})
            self.assertEqual(
                sorted(e["base_commit"] for e in report["key_paths_absent"]), sorted([c1, c2])
            )
            self.assertTrue(
                any("does not exist at base commit" in n for n in report["sharing_notes"]),
                report["sharing_notes"],
            )

    def test_the_run_labels_an_absent_setup_key_path(self):
        with tempfile.TemporaryDirectory() as td:
            results, _run_dir = _run_setup_fixture(
                td, _fix_calc, setup_keys=("package.lock",)
            )
        self.assertIn(rb.SETUP_KEY_ABSENT_LABEL, results["labels"])
        self.assertEqual(
            [e["path"] for e in results["setup"]["key_paths_absent"]], ["package.lock"]
        )

    def test_a_general_mode_task_never_shares_a_template_across_different_injected_bugs(self):
        """The reverse-direction leak. Templates live under `work/`, one `../` from a
        candidate's cwd; a template built from the PRISTINE base while the candidate's sandbox
        carries the injected bug would be a brand-new answer key. Including the task's own
        `setup_patch` in the key is what stops one template being shared across bugs."""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            base = build_harness_fixture_repo(repo)
            templates = rb.GradeTemplates(
                repo, td / "templates", STUB_SETUP_CMD, test_runner=_stub_setup(),
                key_paths=("calc.py",),
            )
            one = {"task_id": "mut-1", "mode": "general", "base_commit": base,
                   "setup_patch": "--- a/calc.py\n+++ b/calc.py\n@@ -2 +2 @@\n-    if x >= 10:\n+    if x > 10:\n"}
            two = dict(one, task_id="mut-2", setup_patch=one["setup_patch"].replace("10", "11"))
            self.assertNotEqual(
                templates.key_for(one), templates.key_for(two),
                "two different injected bugs shared one template",
            )
            self.assertIn("mined setup patch", " ".join(templates.key_basis(one)))


class SetupFailureIsAbsenceNotFailureTests(unittest.TestCase):
    """T17 item 4 — THE MOST IMPORTANT HONESTY RULE IN THE TASK. A broken toolchain that read
    as `not solved` would mark every candidate wrong and produce a confident, entirely
    fictional verdict. Absence is not failure (PLAN D5)."""

    def test_a_failing_setup_makes_the_tests_oracle_unavailable_never_failed(self):
        with tempfile.TemporaryDirectory() as td:
            results, _run_dir = _run_setup_fixture(td, _fix_calc, fail=True)
        cell = next(c for c in results["cells"] if not c["skipped"])
        tests = cell["oracles"]["tests"]
        self.assertFalse(tests["available"])
        self.assertIsNone(tests["passed"], "a broken toolchain rendered as a failed candidate")
        self.assertIn(rb.SETUP_FAILED_NOTE, tests["notes"])
        self.assertIn("exit 7", tests["notes"], "the note does not name the exit code")

    def test_the_envelope_is_labelled_and_the_failure_is_named_in_the_notes(self):
        with tempfile.TemporaryDirectory() as td:
            results, _run_dir = _run_setup_fixture(td, _fix_calc, fail=True)
        self.assertIn(rb.SETUP_FAILED_LABEL, results["labels"])
        self.assertEqual(results["setup"]["templates_failed"], 1)
        self.assertEqual(results["setup"]["templates_prepared"], 1)
        self.assertTrue(
            any("exit 7" in n for n in results["notes"]),
            results["notes"],
        )
        entry = results["setup"]["templates"][0]
        self.assertFalse(entry["ok"])
        self.assertEqual(entry["rc"], 7)
        self.assertIn(rb.SETUP_FAILED_NOTE, entry["note"])

    def test_a_failing_setup_is_prepared_once_and_never_retried_per_grading(self):
        log = []
        with tempfile.TemporaryDirectory() as td:
            _results, _run_dir = _run_setup_fixture(
                td, _fix_calc, models="haiku,sonnet", fail=True, log=log
            )
        self.assertEqual(len(log), 1, "a failing install was retried per grading")

    def test_a_failing_setup_leaves_no_build_tree_or_key_dir_behind(self):
        """T19 item 1 — the T17R verifier confirmed BY HAND that `_prepare`'s
        `shutil.rmtree(self.root / key, ...)` sits OUTSIDE the `if record["ok"]:` block, so a
        setup FAILURE still deletes `work/templates/<key>/build` (and the key dir itself).
        Hand-verification is not coverage: this is the test that would catch a future edit
        moving the rmtree inside the success branch. The failure record must still survive
        with its exit code (`available: False` / `SETUP_FAILED` keeps its evidence)."""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            c1, _c2, _c3 = build_deps_fixture_repo(repo)
            templates = rb.GradeTemplates(
                repo, td / "templates", STUB_SETUP_CMD, test_runner=_stub_setup(fail=True),
            )
            self.addCleanup(templates.cleanup)
            record = templates.prepare(_deps_task("t1", c1))

            key_dir = td / "templates" / record["key"]
            self.assertFalse(key_dir.exists(), "the key dir survived a setup failure")
            self.assertFalse(
                (key_dir / "build").exists(), "the build tree survived a setup failure"
            )
            self.assertFalse(record["ok"])
            self.assertEqual(record["rc"], 7, "the failure record lost its exit code")

    def test_a_failing_setup_is_not_retried_once_per_base_commit_either(self):
        """T17R/F2 splits templates across base commits, and a FAILED template must not be
        dragged into that: it captured no artifact, so nothing can cross a base — and
        re-running a failing install per base is the pathology the cache exists to remove."""
        log = []
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            c1, c2, _c3 = build_deps_fixture_repo(repo)
            templates = rb.GradeTemplates(
                repo, td / "templates", STUB_SETUP_CMD,
                test_runner=_stub_setup(fail=True, log=log), key_paths=("deps.txt",),
            )
            self.addCleanup(templates.cleanup)
            first = templates.prepare(_deps_task("t1", c1))
            second = templates.prepare(_deps_task("t2", c2))
        self.assertEqual(first["key"], second["key"])
        self.assertFalse(first["ok"])
        self.assertEqual(len(log), 1, "a failing install was retried at the second base commit")

    def test_the_test_command_is_never_run_against_an_uninstalled_substrate(self):
        """The check happens BEFORE the substrate is built and BEFORE `--test-cmd` fires —
        otherwise the oracle would report a `not solved` that measured the toolchain."""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            base = build_harness_fixture_repo(repo)
            task = _oracle_task(base, mode="general", scope_path="calc.py")
            calls = []

            def inner(cmd, cwd):
                calls.append(cmd)
                return 0, "OK"

            templates = rb.GradeTemplates(
                repo, td / "templates", STUB_SETUP_CMD,
                test_runner=_stub_setup(inner=inner, fail=True),
            )
            result = rb.oracle_tests(
                task, "", "setup-tests", _stub_setup(inner=inner, fail=True),
                td / "scratch", target_repo=repo, templates=templates,
            )
        self.assertFalse(result["available"])
        self.assertIsNone(result["passed"])
        self.assertEqual(calls, [], "the test command ran against an uninstalled substrate")

    def test_a_failed_template_refuses_to_overlay_rather_than_overlaying_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            base = build_harness_fixture_repo(repo)
            task = _oracle_task(base, mode="general", scope_path="calc.py")
            templates = rb.GradeTemplates(
                repo, td / "templates", STUB_SETUP_CMD, test_runner=_stub_setup(fail=True),
            )
            with self.assertRaises(ValueError) as ctx:
                templates.overlay(task, td / "anywhere")
        self.assertIn(rb.SETUP_FAILED_NOTE, str(ctx.exception))


class SetupTimeIsNotModelLatencyTests(unittest.TestCase):
    """T17 item 5 — oracle (d) feeds the daily-driver pick. Folding a target's build time into
    a cell's `wall_seconds` would attribute the toolchain's slowness to whichever model
    happened to be graded first."""

    def test_setup_time_is_recorded_separately_and_never_inside_wall_seconds(self):
        with tempfile.TemporaryDirectory() as td:
            results, _run_dir = _run_setup_fixture(
                td, _fix_calc, models="haiku,sonnet", delay=0.05
            )
        setup_seconds = results["setup"]["setup_seconds"]
        self.assertGreaterEqual(setup_seconds, 0.05)
        graded = [c for c in results["cells"] if not c["skipped"]]
        self.assertEqual(len(graded), 2)
        for cell in graded:
            self.assertLess(
                cell["wall_seconds"], setup_seconds,
                "template preparation time leaked into a cell's dispatch latency",
            )

    def test_the_run_states_the_template_accounting_on_stdout(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_harness_fixture_repo(repo)
            store = td / "store"
            args = rb.build_parser().parse_args([
                "run", "--repo", str(repo), "--models", "haiku", "--mode", "general",
                "--test-cmd", "setup-tests", "--setup-cmd", STUB_SETUP_CMD,
                "--store-dir", str(store), "--live", "--max-usd", "1000000",
            ])
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rb.cmd_run(
                    args, runner=_candidate_that(_fix_calc),
                    test_runner=_stub_setup(inner=_needs_setup_test_runner),
                )
            text = out.getvalue()
        self.assertIn("grade templates: 1 prepared", text)
        self.assertIn("reused across 1 grading(s)", text)
        self.assertIn("not in any cell's wall_seconds", text)


class SetupTemplateLifetimeTests(unittest.TestCase):
    """T17 item 6 / T17R F1 — the setup COMMAND runs under the run dir; the captured ARTIFACTS
    do not live there at all, and nothing of either survives a run."""

    def test_the_template_build_area_is_swept_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            _results, run_dir = _run_setup_fixture(td, _fix_calc)
            self.assertFalse(
                (run_dir / "work" / "templates").exists(),
                "the template area survived a run without --keep-work",
            )

    def test_even_keep_work_leaves_no_artifact_under_the_run_dir(self):
        """T17R/F1 — `--keep-work` preserves the run's OWN working area, and the artifact store
        is deliberately not part of it. The build tree is gone either way: it is a second copy
        of the state the candidate starts in."""
        with tempfile.TemporaryDirectory() as td:
            _results, run_dir = _run_setup_fixture(td, _fix_calc, keep_work=True)
            templates_root = run_dir / "work" / "templates"
            for key_dir in (templates_root.iterdir() if templates_root.is_dir() else ()):
                self.assertFalse(
                    (key_dir / "build").exists(),
                    "the template's build tree — a second copy of the candidate's own base "
                    "state — was left one `../` from a candidate's cwd",
                )
            self.assertEqual(
                [
                    str(p.relative_to(run_dir)) for p in run_dir.rglob("*")
                    if p.is_file() and p.name == Path(SETUP_ARTIFACT).name
                ],
                [],
                "a captured setup artifact was left under the run dir",
            )
            bodies = [
                str(p.relative_to(run_dir)) for p in run_dir.rglob("*")
                if p.is_file() and _reads_as(p) == SETUP_ARTIFACT_BODY
            ]
            self.assertEqual(bodies, [], "the artifact's CONTENT survived under the run dir")

    def test_the_setup_command_runs_under_the_run_dir_and_never_a_system_temp_dir(self):
        """PLAN D3/D11 — `--setup-cmd` executes arbitrary code from/for the target, so it runs
        exactly where every other arbitrary-code path in this tool runs: under the run's own
        working area."""
        log = []
        with tempfile.TemporaryDirectory() as td:
            _results, run_dir = _run_setup_fixture(td, _fix_calc, log=log)
        self.assertTrue(log, "setup never ran at all")
        for cwd in log:
            self.assertTrue(
                Path(cwd).is_relative_to(run_dir / "work" / "templates"),
                f"the setup command ran outside <run-dir>/work/templates: {cwd}",
            )


class SetupAbsentIsUnchangedBehaviourTests(unittest.TestCase):
    """T17 — absent `--setup-cmd` must be byte-identical to the tool as it was before."""

    def test_no_template_area_and_no_setup_block_without_the_flag(self):
        with tempfile.TemporaryDirectory() as td:
            results, run_dir = _run_setup_fixture(
                td, _fix_calc, setup_cmd=None, keep_work=True,
                test_runner=_harness_test_runner,
            )
        self.assertNotIn("setup", results)
        self.assertFalse((run_dir / "work" / "templates").exists())
        for label in results["labels"]:
            self.assertNotIn("setup", label)
        for note in results["notes"]:
            self.assertNotIn("--setup-cmd", note)

    def test_the_grading_helpers_still_default_to_no_templates(self):
        for fn in (rb.prepare_cell_sandbox, rb.build_grade_substrate, rb.oracle_tests,
                   rb.oracle_tests_red_check):
            with self.subTest(fn=fn.__name__):
                self.assertIsNone(inspect.signature(fn).parameters["templates"].default)


class SetupRunnerSeamTests(unittest.TestCase):
    """T17 item 1/7 — the setup command rides the SAME injectable seam `--test-cmd` uses, and
    NO test in this file may invoke a real installer or the network."""

    def test_the_setup_command_goes_through_the_injected_test_runner(self):
        seen = []

        def runner(cmd, cwd):
            seen.append(cmd)
            return _stub_setup(inner=_needs_setup_test_runner)(cmd, cwd)

        with tempfile.TemporaryDirectory() as td:
            td2 = Path(td)
            repo = td2 / "target"
            build_harness_fixture_repo(repo)
            store = td2 / "store"
            args = rb.build_parser().parse_args([
                "run", "--repo", str(repo), "--models", "haiku", "--mode", "general",
                "--test-cmd", "setup-tests", "--setup-cmd", STUB_SETUP_CMD,
                "--store-dir", str(store), "--live", "--max-usd", "1000000",
            ])
            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_run(args, runner=_candidate_that(_fix_calc), test_runner=runner)
        self.assertIn(STUB_SETUP_CMD, seen)
        self.assertIn("setup-tests", seen)

    def test_no_default_runner_is_ever_constructed_by_the_template_cache_itself(self):
        """`GradeTemplates` falls back to `default_test_runner` only when a caller hands it
        None — `cmd_run` always injects, and every test here injects a stub."""
        self.assertIs(
            inspect.signature(rb.GradeTemplates.__init__).parameters["test_runner"].default,
            None,
        )

    def test_the_engine_never_invents_a_setup_command(self):
        """There is no default, no inference, and no fallback: absent the flag, nothing runs.
        (That no TEST reaches a real installer is enforced from outside, by T17's own verify
        block — a scan for installer names cannot live in the file it scans.)"""
        args = rb.build_parser().parse_args(["run", "--repo", ".", "--models", "haiku"])
        self.assertIsNone(args.setup_cmd)
        source = inspect.getsource(rb.cmd_run)
        self.assertIn('getattr(args, "setup_cmd", None)', source)
        self.assertIn("if setup_cmd:", source)


#: T17R/F1 — the forgery the post-completion review reproduced end to end, as a dispatch runner.
#: A candidate that changes NOTHING in its own sandbox reaches one `../` out of its cwd, finds
#: the shared artifact store, and overwrites the bytes every later grade substrate is built from.
#: `found` records what the sweep could reach — the assertion is that it reaches nothing.
def _artifact_store_raider(found, *, poison=True, marker=FORGERY_MARKER):
    def runner(argv, cwd):
        cwd = Path(cwd)
        if not (cwd / "calc.py").exists():          # the judge's empty cwd
            return 0, _canned_result_json()
        for depth in ("..", "../.."):
            root = (cwd / depth).resolve()
            for path in sorted(root.rglob("*")):
                if not path.is_file():
                    continue
                text = _reads_as(path)
                if text is None or SETUP_ARTIFACT_BODY not in text:
                    continue
                found.append(str(path.relative_to(root)))
                if poison:
                    path.write_text(f"# {marker}\n")
        return 0, _canned_result_json()
    return runner


def _forged_artifact_test_runner(cmd, cwd):
    """Green the moment the installed artifact carries the forgery marker — so a poisoned store
    reaching a substrate really would buy a `solved`, rather than being a pantomime."""
    artifact = Path(cwd) / SETUP_ARTIFACT
    if not artifact.exists():
        return 3, "FAIL: dependencies are not installed (run the setup command first)"
    if FORGERY_MARKER in artifact.read_text():
        return 0, "OK (forged through the setup artifact)"
    return _harness_test_runner(cmd, cwd)


class _RecordingTemplates(rb.GradeTemplates):
    """Remembers every artifact-store root it created, so a test can assert it was deleted."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.store_roots = []

    def store_root(self):
        root = super().store_root()
        if root not in self.store_roots:
            self.store_roots.append(root)
        return root


class _TamperingTemplates(rb.GradeTemplates):
    """Poisons its OWN artifact store once a grading has been served.

    The store now lives outside the run dir under a name no candidate can read, so a dispatch
    runner cannot reach it any more — which is the point of T17R's first mechanism. This
    subclass reaches it from inside the engine instead, so the SECOND mechanism (content hashes
    verified before every overlay) is exercised on its own rather than being untestable because
    the first one works.
    """

    def prepare(self, task):
        record = super().prepare(task)
        if record["ok"] and record["gradings_served"] >= 1:
            (Path(record["path"]) / SETUP_ARTIFACT).write_text(f"# {FORGERY_MARKER}\n")
        return record


class SetupArtifactStoreIsOutOfCandidateReachTests(unittest.TestCase):
    """T17R/F1 + F3 — THE STORE'S LIFETIME, not just how a template is built.

    T17's three mechanisms all guard template CONSTRUCTION (nothing a candidate wrote is an
    input). The defect that shipped was that the captured artifacts then sat under
    `<run-dir>/work/templates/<key>/artifacts` for the WHOLE run, one `../` from every
    candidate's cwd, and `overlay` re-read them from disk on every grading — writable in one
    direction, readable in the other.
    """

    def test_a_candidate_cannot_reach_the_store_to_forge_a_solved(self):
        found = []
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_harness_fixture_repo(repo)
            store = td / "store"
            args = rb.build_parser().parse_args([
                "run", "--repo", str(repo), "--models", "haiku,sonnet", "--mode", "general",
                "--test-cmd", "forge-tests", "--setup-cmd", STUB_SETUP_CMD,
                "--store-dir", str(store), "--live", "--max-usd", "1000000",
            ])
            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_run(
                    args, runner=_artifact_store_raider(found),
                    test_runner=_stub_setup(inner=_forged_artifact_test_runner),
                )
            results = json.loads(
                (Path(rb.list_runs(store)[0][0]["path"]) / "results.json").read_text()
            )
        self.assertEqual(
            found, [],
            f"a candidate reached the prepared setup artifacts from its own sandbox: {found}",
        )
        graded = [c for c in results["cells"] if not c["skipped"]]
        self.assertEqual(len(graded), 2)
        for cell in graded:
            self.assertFalse(
                cell["oracles"]["tests"]["passed"],
                "a candidate that changed nothing in its sandbox forged a `solved`",
            )
        # …and it left no trace either way: both evidence fields would have stayed empty.
        self.assertEqual(results["setup"]["artifacts_tampered"], [])
        self.assertFalse(results["setup"]["artifact_store_under_run_dir"])

    def test_a_candidate_cannot_read_another_tasks_prepared_artifacts(self):
        """F3, the READ direction: a template retained for task 1 used to be a pristine copy of
        exactly the files task 2's candidate was asked to repair. The sweep looks for the
        installed content anywhere it can reach and must come back empty."""
        found = []
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_two_fix_repo(repo)
            store = td / "store"
            args = rb.build_parser().parse_args([
                "run", "--repo", str(repo), "--models", "haiku", "--mode", "issue-replay",
                "--test-cmd", "two-fix-tests", "--setup-cmd", STUB_SETUP_CMD,
                "--store-dir", str(store), "--live", "--max-usd", "1000000",
            ])
            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_run(
                    args, runner=_artifact_store_raider(found, poison=False),
                    test_runner=_stub_setup(inner=_two_fix_test_runner),
                )
            results = json.loads(
                (Path(rb.list_runs(store)[0][0]["path"]) / "results.json").read_text()
            )
        self.assertEqual(found, [], f"a candidate read another task's prepared artifacts: {found}")
        # The multi-task shape F1/F2/F3 all need in order to manifest really was in play.
        self.assertGreaterEqual(len({c["task_id"] for c in results["cells"]}), 2)
        self.assertGreaterEqual(results["setup"]["templates_prepared"], 2)
        self.assertGreaterEqual(results["setup"]["gradings_served"], 2)

    def test_the_store_is_not_under_the_run_dir_and_is_deleted_when_the_run_ends(self):
        roots = []
        original = rb.GradeTemplates

        class Recording(_RecordingTemplates):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                roots.append(self)

        self.addCleanup(setattr, rb, "GradeTemplates", original)
        rb.GradeTemplates = Recording
        with tempfile.TemporaryDirectory() as td:
            _results, run_dir = _run_setup_fixture(td, _fix_calc, keep_work=True)
            self.assertEqual(len(roots), 1)
            store_roots = roots[0].store_roots
            self.assertEqual(len(store_roots), 1, "no artifact store was ever created")
            self.assertFalse(
                store_roots[0].is_relative_to(run_dir),
                f"the artifact store lives under the run dir: {store_roots[0]}",
            )
            self.assertFalse(
                store_roots[0].exists(),
                "the artifact store survived the run (--keep-work keeps the RUN's working "
                "area, not a store that deliberately does not live there)",
            )

    def test_the_setup_command_still_runs_under_the_run_dir(self):
        """The carve-out is narrow on purpose: only the INERT captured bytes move out. Arbitrary
        setup code is the mutation PLAN D3/D11 governs and it stays where every other
        arbitrary-code path in this tool runs."""
        log = []
        with tempfile.TemporaryDirectory() as td:
            _results, run_dir = _run_setup_fixture(td, _fix_calc, log=log)
        self.assertTrue(log, "setup never ran at all")
        for cwd in log:
            self.assertTrue(
                Path(cwd).is_relative_to(run_dir / "work" / "templates"),
                f"the setup command ran outside <run-dir>/work/templates: {cwd}",
            )


class SetupArtifactVerificationTests(unittest.TestCase):
    """T17R/F1's SECOND, INDEPENDENT mechanism. Two mechanisms because this is the sixth ring of
    this leak family and every previous single fix was one ring short — so this one is exercised
    on its own, with the store reached from inside the engine rather than from a sandbox."""

    def test_a_tampered_artifact_makes_the_oracle_unavailable_never_failed(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            base = build_harness_fixture_repo(repo)
            task = _oracle_task(base, mode="general", scope_path="calc.py")
            calls = []

            def inner(cmd, cwd):
                calls.append(cmd)
                return 0, "OK"

            templates = rb.GradeTemplates(
                repo, td / "templates", STUB_SETUP_CMD, test_runner=_stub_setup(inner=inner),
            )
            self.addCleanup(templates.cleanup)
            record = templates.prepare(task)
            (Path(record["path"]) / SETUP_ARTIFACT).write_text(f"# {FORGERY_MARKER}\n")

            result = rb.oracle_tests(
                task, "", "setup-tests", _stub_setup(inner=inner), td / "scratch",
                target_repo=repo, templates=templates,
            )
        self.assertFalse(result["available"])
        self.assertIsNone(result["passed"], "a tampered store rendered as a failed candidate")
        self.assertIn(rb.ARTIFACT_TAMPERED_NOTE, result["notes"])
        # The captured ENTRY is the collapsed directory (`_setup_artifact_paths` records a new
        # directory as itself), so that is what the note names — and a file edited anywhere
        # inside it changes the directory's manifest digest, which is the whole point.
        self.assertIn(SETUP_ARTIFACT_ROOT, result["notes"])
        self.assertEqual(calls, [], "the test command ran against an unverified substrate")

    def test_overlay_refuses_rather_than_trusting_a_caller_that_skipped_the_check(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            base = build_harness_fixture_repo(repo)
            task = _oracle_task(base, mode="general", scope_path="calc.py")
            templates = rb.GradeTemplates(
                repo, td / "templates", STUB_SETUP_CMD, test_runner=_stub_setup(),
            )
            self.addCleanup(templates.cleanup)
            record = templates.prepare(task)
            (Path(record["path"]) / SETUP_ARTIFACT).write_text("padded to a different digest\n")
            with self.assertRaises(ValueError) as ctx:
                templates.overlay(task, td / "anywhere")
        self.assertIn(rb.ARTIFACT_TAMPERED_NOTE, str(ctx.exception))

    def test_a_deleted_artifact_is_caught_too(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            base = build_harness_fixture_repo(repo)
            task = _oracle_task(base, mode="general", scope_path="calc.py")
            templates = rb.GradeTemplates(
                repo, td / "templates", STUB_SETUP_CMD, test_runner=_stub_setup(),
            )
            self.addCleanup(templates.cleanup)
            record = templates.prepare(task)
            (Path(record["path"]) / SETUP_ARTIFACT).unlink()
            self.assertEqual(templates.verify(record), [SETUP_ARTIFACT_ROOT])

    def test_the_run_labels_a_store_that_failed_verification(self):
        original = rb.GradeTemplates
        self.addCleanup(setattr, rb, "GradeTemplates", original)
        rb.GradeTemplates = _TamperingTemplates
        with tempfile.TemporaryDirectory() as td:
            results, _run_dir = _run_setup_fixture(
                td, lambda cwd: None, models="haiku,sonnet",
                test_runner=_forged_artifact_test_runner,
            )
        graded = [c for c in results["cells"] if not c["skipped"]]
        self.assertEqual(len(graded), 2)
        poisoned = graded[1]["oracles"]["tests"]
        self.assertFalse(poisoned["available"])
        self.assertIsNone(poisoned["passed"], "a tampered store bought a grade")
        self.assertIn(rb.ARTIFACT_TAMPERED_NOTE, poisoned["notes"])
        self.assertIn(rb.ARTIFACT_TAMPERED_LABEL, results["labels"])
        self.assertTrue(results["setup"]["artifacts_tampered"], results["setup"])


def build_compiled_fixture_repo(root):
    """Two commits sharing an identical dependency manifest while their SOURCE differs — the
    shape `--setup-key` is aimed at, and the shape a COMPILING setup command makes unsound.
    Returns (base_a, base_b)."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    (root / "deps.txt").write_text("libfoo==1.0\n")
    (root / "app.py").write_text("VERSION = 'A'\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "a: version A")
    base_a = _git(root, "rev-parse", "HEAD").strip()

    (root / "app.py").write_text("VERSION = 'B'\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "b: version B, same deps")
    base_b = _git(root, "rev-parse", "HEAD").strip()
    return base_a, base_b


def _compiling_setup(cmd, cwd):
    """A BUILD step: its output is a function of the SOURCE, not of the keyed manifest."""
    cwd = Path(cwd)
    dist = cwd / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "app.py").write_text((cwd / "app.py").read_text())
    return 0, "built dist/app.py from source"


def _rewriting_setup(cmd, cwd):
    """A setup step that REWRITES A TRACKED FILE — build output by any other name."""
    cwd = Path(cwd)
    (cwd / "app.py").write_text((cwd / "app.py").read_text() + "COMPILED = True\n")
    return 0, "rewrote app.py in place"


class SetupKeySharingSoundnessTests(unittest.TestCase):
    """T17R/F2 — `--setup-key` is UNSOUND for build output, not merely risky.

    Reproduced by the post-completion review: two tasks with different base commits sharing one
    key, task B's substrate carrying task A's `dist/app.py`. On a compiled target that means B's
    grade measures A's source and B's own candidate patch is irrelevant. Both refusals below are
    structural — no flag, no documentation, nothing for a user to remember.
    """

    def test_a_compiling_setup_never_carries_one_tasks_build_output_onto_another(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            base_a, base_b = build_compiled_fixture_repo(repo)
            templates = rb.GradeTemplates(
                repo, td / "templates", "stub-build", test_runner=_compiling_setup,
                key_paths=("deps.txt",),
            )
            self.addCleanup(templates.cleanup)
            built = {}
            for label, base in (("A", base_a), ("B", base_b)):
                task = {"task_id": f"t{label}", "mode": "issue-replay", "base_commit": base,
                        "setup_patch": None, "reference_patch": "", "test_blobs": {}}
                dest = td / f"substrate-{label}"
                rb.build_grade_substrate(task, "", dest, repo, templates=templates)
                built[label] = (
                    (Path(dest) / "app.py").read_text().strip(),
                    (Path(dest) / "dist" / "app.py").read_text().strip(),
                )
            report = templates.report()

        self.assertEqual(built["A"], ("VERSION = 'A'", "VERSION = 'A'"))
        self.assertEqual(
            built["B"], ("VERSION = 'B'", "VERSION = 'B'"),
            "task B's substrate was graded against task A's build output",
        )
        self.assertEqual(report["templates_prepared"], 2, "the unsound share was not refused")
        self.assertTrue(
            any("produced DIFFERENT artifacts" in n for n in report["sharing_notes"]),
            report["sharing_notes"],
        )

    def test_an_artifact_tracked_at_either_base_is_refused_without_even_probing(self):
        """The brief's floor, and the cheap half of the fix: a rewritten TRACKED file is never a
        shareable install artifact, and refusing it costs no extra preparation."""
        log = []

        def rewriting(cmd, cwd):
            log.append(str(cwd))
            return _rewriting_setup(cmd, cwd)

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            base_a, base_b = build_compiled_fixture_repo(repo)
            templates = rb.GradeTemplates(
                repo, td / "templates", "stub-build", test_runner=rewriting,
                key_paths=("deps.txt",),
            )
            self.addCleanup(templates.cleanup)
            first = templates.prepare(
                {"task_id": "tA", "mode": "issue-replay", "base_commit": base_a,
                 "setup_patch": None}
            )
            second = templates.prepare(
                {"task_id": "tB", "mode": "issue-replay", "base_commit": base_b,
                 "setup_patch": None}
            )
            report = templates.report()

        self.assertEqual(first["artifacts"], ["app.py"])
        self.assertNotEqual(
            first["key"], second["key"],
            "a rewritten tracked file was carried onto another task's base",
        )
        self.assertEqual(len(log), 2, "the refusal cost more than the dedicated preparation")
        self.assertTrue(
            any("tracked at a base commit" in n for n in report["sharing_notes"]),
            report["sharing_notes"],
        )

    def test_the_refusal_and_the_verification_both_reach_the_envelope(self):
        with tempfile.TemporaryDirectory() as td:
            results, _run_dir = _run_setup_fixture(td, _fix_calc, setup_keys=("calc.py",))
        self.assertIn("sharing_notes", results["setup"])
        self.assertIn(rb.ARTIFACT_STORE_NOTE, results["notes"])


class SetupArtifactCaptureTests(unittest.TestCase):
    """T17 — the artifact snapshot: what `--setup-cmd` produced, and nothing else."""

    def test_a_whole_new_directory_is_captured_as_itself(self):
        before = {"a.py": ("file", 1, 1)}
        after = {
            "a.py": ("file", 1, 1),
            "node_modules": ("dir",),
            "node_modules/x": ("dir",),
            "node_modules/x/index.js": ("file", 2, 2),
        }
        self.assertEqual(rb._setup_artifact_paths(before, after), ["node_modules"])

    def test_a_rewritten_existing_file_is_captured_individually(self):
        before = {"a.py": ("file", 1, 1), "d": ("dir",)}
        after = {"a.py": ("file", 9, 9), "d": ("dir",), "d/new.txt": ("file", 1, 1)}
        self.assertEqual(rb._setup_artifact_paths(before, after), ["a.py", "d/new.txt"])

    def test_an_untouched_tree_yields_no_artifacts(self):
        index = {"a.py": ("file", 1, 1), "d": ("dir",)}
        self.assertEqual(rb._setup_artifact_paths(index, dict(index)), [])

    def test_the_index_prunes_git_and_records_symlinks_without_descending(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            (td / ".git").mkdir()
            (td / ".git" / "HEAD").write_text("ref: refs/heads/bench\n")
            (td / "pkg").mkdir()
            (td / "pkg" / "m.py").write_text("x = 1\n")
            os.symlink(str(td / "pkg"), str(td / "link"))
            index = rb._tree_index(td)
        self.assertIn("pkg/m.py", index)
        self.assertEqual(index["link"][0], "symlink")
        self.assertNotIn("link/m.py", index)
        self.assertFalse([k for k in index if k.startswith(".git")])


class CalibrationRowsTests(unittest.TestCase):
    """T18 -- `_calibration_rows`/`build_calibration`: the honest reader over prior runs' own
    `usd_basis: "actual"` cells. Real ratios from the kit's first live run (recorded in
    NOTES.md, not read from any real store here): size S, haiku 8.7x, sonnet 10.6x, opus
    11.9x, three cells in one run."""

    def _write_live_run(self, store):
        return _write_run(
            store,
            [
                _v_cell("issue-11570", "fake-alpha-1", usd=0.5203, estimated_usd=0.06),
                _v_cell("issue-11570", "fake-beta-1", usd=1.2760, estimated_usd=0.12),
                _v_cell("issue-11570", "fake-gamma-1", usd=3.5838, estimated_usd=0.30),
            ],
            profiles={"issue-11570": "S"},
        )

    def test_store_dir_none_yields_no_rows(self):
        self.assertEqual(rb._calibration_rows(None), [])

    def test_absent_store_dir_yields_no_rows(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(rb._calibration_rows(Path(td) / "nope"), [])

    def test_empty_store_dir_yields_no_rows(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(rb._calibration_rows(Path(td)), [])

    def test_estimated_basis_cells_never_contribute_a_ratio(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            _write_run(
                store,
                [_v_cell("t1", "fake-alpha-1", usd=0.5, estimated_usd=0.06, usd_basis="estimated")],
                profiles={"t1": "S"},
            )
            self.assertEqual(rb._calibration_rows(store), [])

    def test_skipped_cells_never_contribute_a_ratio(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            _write_run(
                store, [_v_cell("t1", "fake-alpha-1", skipped=rb.SKIPPED_COST_CEILING)],
                profiles={"t1": "S"},
            )
            self.assertEqual(rb._calibration_rows(store), [])

    def test_three_real_cells_yield_three_rows_with_size_joined_from_plan_json(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            self._write_live_run(store)
            rows = rb._calibration_rows(store)
            self.assertEqual(len(rows), 3)
            self.assertTrue(all(r["size_profile"] == "S" for r in rows))
            by_model = {r["model"]: r["ratio"] for r in rows}
            self.assertAlmostEqual(by_model["fake-alpha-1"], 0.5203 / 0.06, places=4)
            self.assertAlmostEqual(by_model["fake-beta-1"], 1.2760 / 0.12, places=4)
            self.assertAlmostEqual(by_model["fake-gamma-1"], 3.5838 / 0.30, places=4)

    def test_row_missing_a_size_profile_join_still_counts_overall_but_not_by_size(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            # no `profiles=` -> no plan.json -> `_task_size_profiles` finds nothing.
            _write_run(store, [_v_cell("unjoined", "fake-alpha-1", usd=0.6, estimated_usd=0.1)])
            rows = rb._calibration_rows(store)
            self.assertEqual(len(rows), 1)
            self.assertIsNone(rows[0]["size_profile"])
            card = rb.build_calibration(store)
            self.assertEqual(card["n_cells"], 1)
            self.assertEqual(card["by_size"], {})  # never attributed to a size it can't prove


class BuildCalibrationTests(unittest.TestCase):
    """T18 -- the plan-card-facing shape: median ratio, sample size, per-size/per-model
    breakdown, and the always-present label list."""

    def test_no_history_reports_unavailable_and_a_visible_label(self):
        with tempfile.TemporaryDirectory() as td:
            card = rb.build_calibration(Path(td) / "empty-store")
            self.assertFalse(card["available"])
            self.assertEqual(card["n_cells"], 0)
            self.assertIsNone(card["overall_ratio"])
            self.assertEqual(card["by_size"], {})
            self.assertEqual(card["by_model"], {})
            self.assertEqual(card["labels"], [rb.CALIBRATION_NONE_LABEL])
            self.assertIn("UNVALIDATED", card["labels"][0])

    def test_none_store_dir_reports_the_same_unavailable_shape(self):
        self.assertEqual(rb.build_calibration(None), rb.build_calibration(None))
        card = rb.build_calibration(None)
        self.assertFalse(card["available"])
        self.assertEqual(card["labels"], [rb.CALIBRATION_NONE_LABEL])

    def test_three_size_s_cells_report_the_measured_median_and_sample_size(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            _write_run(
                store,
                [
                    _v_cell("issue-11570", "fake-alpha-1", usd=0.5203, estimated_usd=0.06),
                    _v_cell("issue-11570", "fake-beta-1", usd=1.2760, estimated_usd=0.12),
                    _v_cell("issue-11570", "fake-gamma-1", usd=3.5838, estimated_usd=0.30),
                ],
                profiles={"issue-11570": "S"},
            )
            card = rb.build_calibration(store)
            self.assertTrue(card["available"])
            self.assertEqual(card["n_cells"], 3)
            self.assertEqual(card["n_runs"], 1)
            # median of {8.67, 10.63, 11.95} is sonnet's own ratio
            self.assertAlmostEqual(card["overall_ratio"], 1.2760 / 0.12, places=4)
            self.assertEqual(set(card["by_size"]), {"S"})
            self.assertEqual(card["by_size"]["S"]["n"], 3)
            self.assertEqual(set(card["by_model"]), {"fake-alpha-1", "fake-beta-1", "fake-gamma-1"})
            for model in card["by_model"]:
                self.assertEqual(card["by_model"][model]["n"], 1)
            label_text = " ".join(card["labels"])
            self.assertIn("3 cell(s) in 1 run(s)", label_text)
            self.assertIn("S=", label_text)

    def test_a_size_s_sample_never_bleeds_into_a_size_l_breakdown(self):
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            # One run, size S, high ratio; a second run, size L, a very different ratio --
            # T18 do-2: a thin S sample must not be presented as applying to L.
            _write_run(
                store,
                [_v_cell("s-task", "fake-alpha-1", usd=0.52, estimated_usd=0.06)],
                profiles={"s-task": "S"},
            )
            _write_run(
                store,
                [_v_cell("l-task", "fake-alpha-1", usd=1.0, estimated_usd=0.5)],
                profiles={"l-task": "L"},
            )
            card = rb.build_calibration(store)
            self.assertEqual(card["n_cells"], 2)
            self.assertEqual(card["n_runs"], 2)
            self.assertEqual(set(card["by_size"]), {"S", "L"})
            self.assertAlmostEqual(card["by_size"]["S"]["ratio"], 0.52 / 0.06, places=4)
            self.assertAlmostEqual(card["by_size"]["L"]["ratio"], 1.0 / 0.5, places=4)
            self.assertEqual(card["by_size"]["S"]["n"], 1)
            self.assertEqual(card["by_size"]["L"]["n"], 1)

    def test_calibration_never_touches_the_matrix_estimate(self):
        # T18 do-1: report, never silently adjust -- proven at the `build_plan` level below,
        # this proves the calibration reader itself carries no such side channel.
        card = rb.build_calibration(None)
        self.assertNotIn("estimated_usd", card)
        self.assertNotIn("grand_total", card)


class PlanCalibrationIntegrationTests(unittest.TestCase):
    """T18 -- `build_plan`'s `store_dir` plumbing: the raw estimate is untouched, the
    calibration line rides beside it, and absence is exactly as visible as presence."""

    def test_no_store_dir_given_to_build_plan_reports_unavailable(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_fixture_repo(repo)
            card = rb.build_plan(repo, ["haiku"], scratch_dir=td / "scratch")
            self.assertFalse(card["calibration"]["available"])
            self.assertEqual(card["calibration"]["labels"], [rb.CALIBRATION_NONE_LABEL])

    def test_a_populated_store_feeds_the_calibration_line_without_touching_the_estimate(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_fixture_repo(repo)
            store = td / "store"
            _write_run(
                store,
                [_v_cell("issue-11570", "fake-alpha-1", usd=0.5203, estimated_usd=0.06)],
                profiles={"issue-11570": "S"},
            )
            card_uncalibrated = rb.build_plan(repo, ["haiku"], scratch_dir=td / "scratch-1")
            card_calibrated = rb.build_plan(
                repo, ["haiku"], scratch_dir=td / "scratch-2", store_dir=store,
            )
            # T18 do-1/acceptance: the raw estimate (matrix + totals) is UNCHANGED regardless
            # of whether calibration data exists.
            self.assertEqual(
                card_uncalibrated["totals"]["grand_total"], card_calibrated["totals"]["grand_total"],
            )
            self.assertEqual(card_uncalibrated["matrix"], card_calibrated["matrix"])
            self.assertFalse(card_uncalibrated["calibration"]["available"])
            self.assertTrue(card_calibrated["calibration"]["available"])
            self.assertEqual(card_calibrated["calibration"]["n_cells"], 1)

    def test_rendered_markdown_always_carries_a_calibration_section(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_fixture_repo(repo)
            card = rb.build_plan(repo, ["haiku"], scratch_dir=td / "scratch")
            text = rb.render_plan_markdown(card)
            self.assertIn("## calibration", text)
            self.assertIn(rb.CALIBRATION_NONE_LABEL, text)


class PlanCliCalibrationTests(unittest.TestCase):
    """T18 -- the CLI surface: `--store-dir` on `plan` feeds the calibration line and is
    opt-in, never a silent fallback to the real `benchruns/` store (mirrors the existing
    `PlanCliTests.test_plan_never_writes_the_real_store` posture, for reads)."""

    def test_plan_without_store_dir_never_reads_the_real_store(self):
        # Proven indirectly: the real store is untouched (existing invariant) AND the printed
        # calibration line is the "no data" one even if this machine's real benchruns/ store
        # happens to hold prior runs -- `plan` must not have looked at it.
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_fixture_repo(repo)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rb.main(["plan", "--repo", str(repo), "--models", "haiku"])
            text = out.getvalue()
            self.assertIn(rb.CALIBRATION_NONE_LABEL, text)

    def test_plan_with_store_dir_prints_the_measured_ratio(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_fixture_repo(repo)
            store = td / "store"
            _write_run(
                store,
                [
                    _v_cell("issue-11570", "fake-alpha-1", usd=0.5203, estimated_usd=0.06),
                    _v_cell("issue-11570", "fake-beta-1", usd=1.2760, estimated_usd=0.12),
                    _v_cell("issue-11570", "fake-gamma-1", usd=3.5838, estimated_usd=0.30),
                ],
                profiles={"issue-11570": "S"},
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rb.main([
                    "plan", "--repo", str(repo), "--models", "haiku", "--store-dir", str(store),
                ])
            text = out.getvalue()
            self.assertIn("3 cell(s) in 1 run(s)", text)
            self.assertNotIn(rb.CALIBRATION_NONE_LABEL, text)

    def test_plan_json_output_carries_the_calibration_key(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_fixture_repo(repo)
            store = td / "store"
            _write_run(
                store, [_v_cell("t1", "fake-alpha-1", usd=0.6, estimated_usd=0.06)],
                profiles={"t1": "S"},
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rb.main([
                    "plan", "--repo", str(repo), "--models", "haiku", "--store-dir", str(store),
                    "--json",
                ])
            card = json.loads(out.getvalue())
            self.assertTrue(card["calibration"]["available"])
            self.assertEqual(card["calibration"]["n_cells"], 1)


# ---------------------------------------------------------------------------------------------
# T20 — the full-patch DIAGNOSTIC. Same fixture family as `HarnessForgeryTests` on purpose: the
# whitelist those tests pin is precisely what produces the false negatives these tests bound, and
# the forgery they proved harmless must STAY harmless now that a second substrate applies it.
#
# `build_harness_fixture_repo` gives three shapes off one repo:
#   * fix `calc.py`      -> in scope -> genuinely `solved` (diagnostic must not run at all)
#   * fix `alt.py`       -> out of scope, but the suite really passes -> THE PYRIGHT PATTERN
#   * rewrite `run_tests.py` -> out of scope, suite passes for the wrong reason -> THE FORGERY
# The last two are indistinguishable to the diagnostic BY CONSTRUCTION. That is why it bounds
# and never scores.


def _run_harness_fixture_pair(td, mutate):
    """The same stubbed general-mode run twice — diagnostic ON, then OFF.

    -> `((on_results, on_run_dir), (off_results, off_run_dir))`. Both runs build a FRESH
    fixture repo of their own, so the only difference between them is the flag. The OFF run IS
    the pre-T20 behaviour, which is what makes it a usable baseline for "the diagnostic moved
    nothing".
    """
    td = Path(td)
    return (
        _run_general_harness_fixture(td / "on", mutate),
        _run_general_harness_fixture(td / "off", mutate, no_full_patch_check=True),
    )


class FullPatchDiagnosticTests(unittest.TestCase):
    """T20 — bound the false negatives; never reopen the forgery."""

    # -- the population it exists for -------------------------------------------------------

    def test_a_correct_fix_in_an_out_of_scope_file_reads_not_solved_and_the_diagnostic_passes(self):
        """THE PYRIGHT PATTERN, which is why this task exists at all.

        In the first completed live run, 9 of 14 cells carried `not solved` WITH work reverted
        from outside the reference patch's scope — one of them a plausible, genuinely-fixing
        edit to a different source file. `alt.py` is that shape: the stub suite really does pass
        because of it, and the in-scope grade really must still read `not solved`.
        """
        with tempfile.TemporaryDirectory() as td:
            results, run_dir = _run_general_harness_fixture(
                td, lambda cwd: (cwd / "alt.py").write_text('MODE = "PATCHED"\n')
            )
            cell = next(c for c in results["cells"] if not c["skipped"])

            # The in-scope grade is unchanged and stays the routing-grade number.
            self.assertTrue(cell["oracles"]["tests"]["available"])
            self.assertFalse(cell["oracles"]["tests"]["passed"])
            self.assertEqual(cell["candidate_modified_out_of_scope"], ["alt.py"])

            diag = cell["oracles"]["full_patch"]
            self.assertTrue(diag["run"])
            self.assertTrue(diag["available"], diag)
            self.assertTrue(diag["passed"], diag)
            self.assertEqual(diag["applied_out_of_scope"], ["alt.py"])
            self.assertEqual(diag["label"], rb.FULL_PATCH_DIAGNOSTIC_LABEL)
            self.assertIn("NEVER routing-grade", diag["label"])
            self.assertIsNotNone(diag["test_seconds"])

            # …and the BOUND renders with the arithmetic the brief pins.
            card = rb.build_verdict(run_dir, "both", None)
            summary = next(s for s in card["summaries"] if s["candidate"] == cell["model"])
            bound = summary["false_negative_bound"]
            self.assertEqual(bound["objective_n"], 1)
            self.assertEqual(bound["not_solved_n"], 1)
            self.assertEqual(bound["diagnostic_run_n"], 1)
            self.assertEqual(bound["diagnostic_passed_n"], 1)
            self.assertEqual(bound["solved_lower"], summary["solved_n"])
            self.assertEqual(bound["solved_upper"], summary["solved_n"] + 1)

            markdown = rb.render_verdict_markdown(card)
            self.assertIn(
                "false-negative bound: 1 of the 1 not-solved cell(s) pass with the full patch "
                "applied — solved lies in [0, 1] of 1",
                markdown,
            )
            self.assertIn("the upper bound is DIAGNOSTIC (forgeable)", markdown)
            self.assertIn("the lower bound is routing-grade", markdown)
            # The old NOTE cited nothing; it cites the measurement now.
            self.assertIn("diagnostic PASSES — possible false negative", markdown)
            table = markdown.partition("## measurement")[2].partition("## per candidate")[0]
            self.assertIn("full-patch DIAGNOSTIC", table)
            self.assertIn("PASSES — possible false negative", table)

    def test_the_harness_forgery_passes_the_diagnostic_and_moves_nothing_downstream(self):
        """THE FORGERY, and the four things it must NOT be able to move.

        The candidate rewrites the file `--test-cmd` invokes and touches no module and no
        test-pattern path — the Phase 4 reviewer's forgery, verbatim. Its diagnostic passes,
        because the diagnostic applies exactly what the in-scope grade refuses to. That is
        acceptable ONLY because `solved`, the evidence floor, the tier map and the daily-driver
        pick are all provably identical to a run with the diagnostic switched off. Each of the
        four is asserted explicitly rather than inferred from one comparison.
        """
        def forge(cwd):
            (cwd / "run_tests.py").write_text("import sys; sys.exit(0)  # FORGED\n")

        with tempfile.TemporaryDirectory() as td:
            (on, on_dir), (off, off_dir) = _run_harness_fixture_pair(Path(td), forge)
            on_cell = next(c for c in on["cells"] if not c["skipped"])

            # in scope: still not solved, exactly as `HarnessForgeryTests` pins it
            self.assertTrue(on_cell["oracles"]["tests"]["available"])
            self.assertFalse(on_cell["oracles"]["tests"]["passed"])
            self.assertEqual(on_cell["candidate_touched_tests"], [])

            # the diagnostic passes — and names the harness VERBATIM, unclassified
            diag = on_cell["oracles"]["full_patch"]
            self.assertTrue(diag["passed"], diag)
            self.assertEqual(diag["applied_out_of_scope"], ["run_tests.py"])
            self.assertTrue(
                any("run_tests.py" in n and rb.FULL_PATCH_PASSED_NOTE in n
                    for n in on["notes"]),
                on["notes"],
            )
            markdown = rb.render_verdict_markdown(rb.build_verdict(on_dir, "both", None))
            self.assertIn("run_tests.py", markdown)

            # THE FOUR, each asserted on its own rather than through one blanket comparison.
            on_card = rb.build_verdict(on_dir, "both", None)
            off_card = rb.build_verdict(off_dir, "both", None)
            on_sum = next(s for s in on_card["summaries"])
            off_sum = next(s for s in off_card["summaries"])

            # 1. `solved`
            self.assertEqual(on_sum["solved_n"], off_sum["solved_n"])
            self.assertEqual(on_sum["solved_n"], 0)
            self.assertEqual(on_sum["solved_rate"], off_sum["solved_rate"])
            self.assertEqual(on_sum["solved_task_ids"], off_sum["solved_task_ids"])
            self.assertEqual(on_card["capability_order"], off_card["capability_order"])
            # 2. the evidence floor
            self.assertEqual(on_card["below_floor"], off_card["below_floor"])
            self.assertTrue(on_card["below_floor"])
            self.assertEqual(on_sum["objective_n"], off_sum["objective_n"])
            # 3. the tier map
            self.assertEqual(on_card["tier_map"], off_card["tier_map"])
            # 4. the daily-driver pick
            self.assertEqual(
                on_card["daily_driver"]["pick"], off_card["daily_driver"]["pick"]
            )

            # …and `apply` refuses it either way — a passing diagnostic buys no route to prefs.
            prefs = Path(td) / "prefs.json"
            for run_dir in (on_dir, off_dir):
                with contextlib.redirect_stdout(io.StringIO()):
                    rb.cmd_verdict(rb.build_parser().parse_args([
                        "verdict", "--run", run_dir.name,
                        "--store-dir", str(run_dir.parent), "--goal", "both",
                    ]))
                with self.assertRaises(ValueError) as ctx:
                    rb.apply_verdict(run_dir, prefs, rb._cr().load_pricing())
                self.assertIn("below-floor verdict is never applied", str(ctx.exception))
            self.assertFalse(prefs.exists())

    def test_the_conditional_gate_buys_nothing_it_cannot_answer(self):
        """Item 2's gate, all four branches. A diagnostic run costs one more execution of the
        target's arbitrary `--test-cmd` (PLAN D11 exposure, toolchain time), so it is bought
        only for the false-negative SUSPECTS."""
        def fix_in_scope(cwd):
            calc = cwd / "calc.py"
            calc.write_text(calc.read_text().replace("x > 10", "x >= 10"))

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)

            # (a) the in-scope grade PASSED — nothing to bound
            solved, _d = _run_general_harness_fixture(td / "solved", fix_in_scope)
            cell = next(c for c in solved["cells"] if not c["skipped"])
            self.assertTrue(cell["oracles"]["tests"]["passed"])
            self.assertFalse(cell["oracles"]["full_patch"]["run"])
            self.assertEqual(
                cell["oracles"]["full_patch"]["reason"], rb.FULL_PATCH_NOT_RUN_SOLVED
            )

            # (b) no out-of-scope work at all — the two substrates would be the same tree
            nothing, _d = _run_general_harness_fixture(td / "nothing", lambda cwd: None)
            cell = next(c for c in nothing["cells"] if not c["skipped"])
            self.assertFalse(cell["oracles"]["tests"]["passed"])
            self.assertEqual(cell["candidate_modified_out_of_scope"], [])
            self.assertFalse(cell["oracles"]["full_patch"]["run"])
            self.assertEqual(
                cell["oracles"]["full_patch"]["reason"],
                rb.FULL_PATCH_NOT_RUN_NO_OUT_OF_SCOPE,
            )

            # (c) --no-full-patch-check
            off, _d = _run_general_harness_fixture(
                td / "off", lambda cwd: (cwd / "alt.py").write_text('MODE = "PATCHED"\n'),
                no_full_patch_check=True,
            )
            cell = next(c for c in off["cells"] if not c["skipped"])
            self.assertEqual(cell["candidate_modified_out_of_scope"], ["alt.py"])
            self.assertFalse(cell["oracles"]["full_patch"]["run"])
            self.assertEqual(
                cell["oracles"]["full_patch"]["reason"], rb.FULL_PATCH_NOT_RUN_DISABLED
            )

            # (d) the tests oracle was never available — there is no in-scope grade to bound
            self.assertEqual(
                rb.full_patch_not_run_reason({"available": False, "passed": None}, ["x.py"]),
                rb.FULL_PATCH_NOT_RUN_TESTS_UNAVAILABLE,
            )

    def test_a_genuine_failure_adds_nothing_to_the_bound(self):
        """The population's other half: out-of-scope work that does NOT make the suite pass.
        The diagnostic runs, reads `still fails`, and the interval stays degenerate — which is
        the whole reason it is worth running rather than assuming."""
        with tempfile.TemporaryDirectory() as td:
            results, run_dir = _run_general_harness_fixture(
                td, lambda cwd: (cwd / "notes.md").write_text("looked around, gave up\n")
            )
            cell = next(c for c in results["cells"] if not c["skipped"])
            self.assertFalse(cell["oracles"]["tests"]["passed"])
            self.assertEqual(cell["candidate_modified_out_of_scope"], ["notes.md"])
            diag = cell["oracles"]["full_patch"]
            self.assertTrue(diag["run"])
            self.assertTrue(diag["available"])
            self.assertFalse(diag["passed"])

            card = rb.build_verdict(run_dir, "both", None)
            summary = next(s for s in card["summaries"] if s["candidate"] == cell["model"])
            bound = summary["false_negative_bound"]
            self.assertEqual(bound["diagnostic_run_n"], 1)
            self.assertEqual(bound["diagnostic_passed_n"], 0)
            self.assertEqual(bound["solved_upper"], bound["solved_lower"])
            markdown = rb.render_verdict_markdown(card)
            self.assertIn("still fails", markdown)
            self.assertIn("diagnostic still fails with the full patch applied", markdown)

    # -- the rendering mutation check -------------------------------------------------------

    def test_a_passing_diagnostic_cannot_increment_solved_n(self):
        """ITEM 7's mutation check, done at the RENDERING boundary rather than through a run:
        an envelope is constructed in which every cell's in-scope grade FAILED and every cell's
        diagnostic PASSED. If any arithmetic anywhere folded the diagnostic into oracle (a),
        this candidate would read 4/4; `solved` must read 0/4 and every downstream consumer
        must agree with it."""
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            cells = []
            for n in range(4):
                cell = _v_cell(f"t{n}", "fake-alpha-1", passed=False)
                cell["candidate_modified_out_of_scope"] = ["somewhere/else.py"]
                cell["oracles"]["full_patch"] = {
                    "oracle": "tests-full-patch", "run": True, "available": True,
                    "passed": True, "rc": 0, "reason": None,
                    "notes": rb.FULL_PATCH_PASSED_NOTE,
                    "applied_out_of_scope": ["somewhere/else.py"],
                    "restored_test_paths": [], "test_seconds": 0.1,
                    "label": rb.FULL_PATCH_DIAGNOSTIC_LABEL,
                }
                cells.append(cell)
            _run_id, run_dir = _write_run(store, cells)

            card = rb.build_verdict(run_dir, "both", None, min_tasks=4)
            summary = next(s for s in card["summaries"] if s["candidate"] == "fake-alpha-1")
            self.assertEqual(summary["solved_n"], 0, "a diagnostic pass reached `solved_n`")
            self.assertEqual(summary["objective_n"], 4)
            self.assertEqual(summary["solved_rate"], 0.0)
            order = next(
                r for r in card["capability_order"] if r["candidate"] == "fake-alpha-1"
            )
            self.assertEqual(order["solved_n"], 0)
            self.assertEqual(order["solved_rate"], 0.0)
            # …and the bound is present, correct, and clearly the other number.
            bound = summary["false_negative_bound"]
            self.assertEqual((bound["solved_lower"], bound["solved_upper"]), (0, 4))
            self.assertIn(
                "solved lies in [0, 4] of 4", rb.render_verdict_markdown(card)
            )

    # -- isolation (item 6: construction AND lifetime, inverted) ----------------------------

    def test_the_in_scope_grade_is_byte_identical_with_the_diagnostic_on_and_off(self):
        """THE CONTAMINATION PROPERTY. This substrate holds candidate-written bytes BY DESIGN,
        so the leak question inverts: not "can a candidate influence it" but "can it influence
        anything else". The routing-grade grade is the thing that must not move, and it is
        compared as bytes across three candidate shapes — a forgery, an out-of-scope fix, and
        an in-scope fix — rather than argued about.
        """
        shapes = {
            "forgery": lambda cwd: (cwd / "run_tests.py").write_text("# FORGED\n"),
            "out-of-scope-fix": lambda cwd: (cwd / "alt.py").write_text('MODE = "PATCHED"\n'),
            "in-scope-fix": lambda cwd: (cwd / "calc.py").write_text(
                (cwd / "calc.py").read_text().replace("x > 10", "x >= 10")
            ),
        }
        for label, mutate in shapes.items():
            with self.subTest(shape=label):
                with tempfile.TemporaryDirectory() as td:
                    (on, _on_dir), (off, _off_dir) = _run_harness_fixture_pair(Path(td), mutate)
                on_cell = next(c for c in on["cells"] if not c["skipped"])
                off_cell = next(c for c in off["cells"] if not c["skipped"])
                self.assertEqual(
                    json.dumps(on_cell["oracles"]["tests"], sort_keys=True),
                    json.dumps(off_cell["oracles"]["tests"], sort_keys=True),
                    "the diagnostic changed the in-scope grade it is supposed to bound",
                )
                self.assertEqual(
                    on_cell["candidate_modified_out_of_scope"],
                    off_cell["candidate_modified_out_of_scope"],
                )
                self.assertEqual(
                    json.dumps(on_cell["oracles"]["structural"], sort_keys=True),
                    json.dumps(off_cell["oracles"]["structural"], sort_keys=True),
                )
                # …and the OFF run really did skip it, so this is not two identical no-ops.
                self.assertTrue(on_cell["oracles"]["full_patch"]["run"] or label == "in-scope-fix")
                self.assertFalse(off_cell["oracles"]["full_patch"]["run"])

    def test_no_diagnostic_substrate_survives_its_own_grading(self):
        """LIFETIME, checked directly. The substrate carries the candidate's whole patch AND
        the withheld `test_blobs`; it lives under `<run-dir>/work`, one `../` from the next
        candidate's cwd, so it may not outlive the grading that built it — not even under
        `--keep-work`, which preserves cell sandboxes and has nothing to say about a throwaway
        grade tree. `SolutionAncestryTests` checks the same property from the other side, at
        every live dispatch."""
        with tempfile.TemporaryDirectory() as td:
            results, run_dir = _run_general_harness_fixture(
                td, lambda cwd: (cwd / "alt.py").write_text('MODE = "PATCHED"\n'),
                keep_work=True,
            )
            cell = next(c for c in results["cells"] if not c["skipped"])
            self.assertTrue(
                cell["oracles"]["full_patch"]["run"], "no diagnostic ran — nothing was proved"
            )
            leftovers = sorted(
                str(p.relative_to(run_dir)) for p in run_dir.rglob("repo-bench-fullpatch-*")
            )
            self.assertEqual(leftovers, [], f"a diagnostic substrate survived: {leftovers}")

    def test_the_diagnostic_lives_beside_solved_and_never_in_it(self):
        """The structural statement, asserted rather than assumed: the cell key is separate,
        the expanded row keeps them apart, and `_tests_cell_text` — the ONLY renderer of the
        `solved` column — has three legal strings and none of them is the diagnostic's."""
        row = {
            "tests": {"available": True, "solved": False, "notes": ""},
            "full_patch": {
                "run": True, "available": True, "passed": True, "reason": None,
                "applied_out_of_scope": ["x.py"], "restored_test_paths": [],
                "test_seconds": 0.1, "notes": "", "label": rb.FULL_PATCH_DIAGNOSTIC_LABEL,
            },
        }
        self.assertEqual(rb._tests_cell_text(row), "not solved")
        self.assertEqual(rb._full_patch_cell_text(row), "PASSES — possible false negative")
        row["full_patch"]["passed"] = False
        self.assertEqual(rb._full_patch_cell_text(row), "still fails")
        row["full_patch"]["run"] = False
        self.assertEqual(rb._full_patch_cell_text(row), "-")
        row["full_patch"].update(run=True, available=False)
        self.assertEqual(rb._full_patch_cell_text(row), rb.NA)

    def test_a_pre_t20_envelope_renders_the_column_as_not_run_rather_than_crashing(self):
        """Every envelope written before this task has no `full_patch` key at all. That is
        absence, and it renders as `-` with a stated reason — never as a `False` that would
        read as "the diagnostic said no", and never as a KeyError."""
        with tempfile.TemporaryDirectory() as td:
            store = Path(td) / "store"
            _run_id, run_dir = _write_run(store, [_v_cell("t1", "fake-alpha-1", passed=False)])
            card = rb.build_verdict(run_dir, "both", None)
            row = card["measurements"][0]
            self.assertFalse(row["full_patch"]["run"])
            self.assertEqual(row["full_patch"]["reason"], "no diagnostic record in this envelope")
            summary = card["summaries"][0]
            self.assertEqual(summary["false_negative_bound"]["diagnostic_run_n"], 0)
            markdown = rb.render_verdict_markdown(card)
            self.assertIn("an unrun diagnostic bounds nothing", markdown)

    def test_the_diagnostic_still_restores_the_test_surface(self):
        """T7R's law is NOT relaxed by T20. A candidate that rewrites a test-pattern path to
        pass gets that edit stripped from the diagnostic substrate too — the diagnostic widens
        the REFERENCE-SCOPE whitelist and nothing else."""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            base = build_harness_fixture_repo(repo)
            blobs = {"tests/test_calc.py": "# the withheld reference test\n"}
            task = _oracle_task(base, mode="general", blobs=blobs, scope_path="calc.py")

            def mutate(cwd):
                (cwd / "alt.py").write_text('MODE = "PATCHED"\n')
                (cwd / "tests" / "test_calc.py").write_text("# CANDIDATE REWROTE THIS\n")

            patch, _sandbox = _candidate_patch_for(repo, base, mutate, td / "cand")
            built = rb.build_full_patch_substrate(task, patch, td / "substrate", repo)
            self.assertTrue(built["applied"], built["notes"])
            self.assertEqual(built["restored_test_paths"], ["tests/test_calc.py"])
            self.assertEqual(
                (Path(built["path"]) / "tests" / "test_calc.py").read_text(),
                blobs["tests/test_calc.py"],
                "the candidate's test-file edit survived into the diagnostic substrate",
            )
            # …while the out-of-scope module edit — the whole point — did arrive.
            self.assertIn("PATCHED", (Path(built["path"]) / "alt.py").read_text())
            self.assertEqual(built["applied_out_of_scope"], ["alt.py"])

    def test_the_diagnostic_refuses_a_task_with_no_discriminating_oracle(self):
        """Called DIRECTLY, past the gate, on an issue-replay task whose fix touched no tests:
        there are no withheld blobs, so `--test-cmd` would grade the repo's own visible tests
        and pass at base. A bound built from a guaranteed pass is worse than no bound, so the
        oracle reports itself unavailable and `passed` stays `None`."""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            base = build_harness_fixture_repo(repo)
            task = _oracle_task(base, mode="issue-replay", scope_path="calc.py")
            task["oracle_tests_available"] = False
            calls = []
            result = rb.oracle_tests_full_patch(
                task, "", "cmd", lambda cmd, cwd: calls.append(cwd) or (0, "OK"),
                td / "scratch", target_repo=repo,
            )
        self.assertFalse(result["available"])
        self.assertIsNone(result["passed"])
        self.assertEqual(calls, [], "the diagnostic ran a test command it could not read")

    def test_the_diagnostic_dispatches_no_model(self):
        """Item 3, asserted rather than described: this oracle takes no dispatch runner, no
        adapter and no pricing, and its only subprocess seam is the injected `test_runner`. A
        model dispatch would have to appear in its signature to exist."""
        params = set(inspect.signature(rb.oracle_tests_full_patch).parameters)
        for forbidden in ("runner", "adapter", "pricing", "claude_bin", "max_usd", "spent_usd"):
            self.assertNotIn(forbidden, params)
        source = inspect.getsource(rb.oracle_tests_full_patch)
        self.assertNotIn("would_exceed_ceiling(", source)
        self.assertIn("would_exceed_ceiling", source)  # …but the absence is EXPLAINED
        self.assertIn("label", source)


# ---------------------------------------------------------------------------------------------
# T21 — `regrade`. A ceiling stop during the POST-LOOP grading pass is a designed, permanent
# outcome (PLAN D1) that strands the judge leg specifically: every candidate cell dispatched and
# paid for, oracle (c) simply absent for the tail of the matrix. These tests hold the two things
# a second spending invocation over an existing envelope must never get wrong — the spend gate
# is `run`'s, not a second copy of it, and completed work is PROVABLY untouched.
#
# Everything below is offline and free: temp stores, synthetic envelopes written into them (the
# GUARDRAILS-sanctioned shape for a store fixture), fake model ids priced from FIXTURE_PRICING,
# and injected dispatch runners. No binary, no network, no cent.

#: Diff-SHAPED on purpose (the T7R/F4c lesson): a bare string strips to no file blocks at all,
#: which `grade_cells` reads as an empty reference and refuses to dispatch.
_REGRADE_REFERENCE = (
    "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-before\n+after\n"
)
#: A reference that strips to nothing — the `empty-reference` skip, which is NOT a budget
#: casualty and must survive a regrade untouched.
_REGRADE_EMPTY_REFERENCE = (
    "diff --git a/tests/test_a.py b/tests/test_a.py\n--- a/tests/test_a.py\n"
    "+++ b/tests/test_a.py\n@@ -1 +1 @@\n-old\n+new\n"
)

_REGRADE_JUDGE = "fake-opus-1"
_REGRADE_CANDIDATE = "fake-haiku-1"


def _regrade_adapter():
    """CLAUDE_ADAPTER with FIXTURE_PRICING bolted onto its pricing seam — obviously-fake model
    ids, never a real price and never a real roster."""
    return dict(rb.CLAUDE_ADAPTER, load_pricing=lambda: FIXTURE_PRICING)


def _judge_stub_runner(output="GRADE A=correct B=partial EQUIVALENT=no", usage=None, rc=0):
    """An injected dispatch runner for judge grades. `usage=None` (the default) means the
    canned envelope carries no token counts, so each grade's `usd` IS its estimate exactly —
    which is what lets a ceiling test do exact arithmetic instead of directional arithmetic."""
    calls = []

    def runner(argv, cwd):
        calls.append({"argv": list(argv), "cwd": str(cwd)})
        return rc, _canned_result_json(usage) + "\n" + output

    runner.calls = calls
    return runner


def _regrade_task(task_id, reference=_REGRADE_REFERENCE):
    return {
        "task_id": task_id,
        "mode": "issue-replay",
        "statement": f"statement for {task_id}",
        "subject": f"subject for {task_id}",
        "reference_patch": reference,
        "size_profile": "S",
    }


def _write_stranded_run(td, *, judge=_REGRADE_JUDGE, candidates=(_REGRADE_CANDIDATE,),
                        skipped_cell=True, verdict=None, spend=None, write_tasks=True):
    """A run whose judge column was cut mid-pass -> `(store, run_id, run_dir)`.

    Five task×candidate cells, in this deliberate order:

        idx 0  t1  grade COMPLETED               -> must stay byte-identical
        idx 1  t2  grade skipped cost-ceiling    -> PENDING (this is what regrade finishes)
        idx 2  t3  grade skipped empty-reference -> must stay skipped, never re-dispatched
        idx 3  t4  grade skipped cost-ceiling,
                   CELL skipped cost-ceiling     -> unfinishable: no patch to grade
        idx 4  t5  grade skipped cost-ceiling    -> PENDING

    The two pending grades are deliberately NON-ADJACENT (indices 1 and 4) so an implementation
    that rebuilt the list by appending, or that merged positionally without a key, would show up
    as reordering rather than passing by luck.
    """
    store = Path(td) / "store"
    run_id, run_dir = rb.new_run_dir(store)
    cells = [
        _v_cell("t1", _REGRADE_CANDIDATE),
        _v_cell("t2", _REGRADE_CANDIDATE),
        _v_cell("t3", _REGRADE_CANDIDATE),
        (_v_cell("t4", _REGRADE_CANDIDATE, skipped="cost-ceiling") if skipped_cell
         else _v_cell("t4", _REGRADE_CANDIDATE)),
        _v_cell("t5", _REGRADE_CANDIDATE),
    ]
    grades = [
        _v_grade("t1", _REGRADE_CANDIDATE, "correct"),
        _v_grade("t2", _REGRADE_CANDIDATE, None, skipped="cost-ceiling"),
        _v_grade(
            "t3", _REGRADE_CANDIDATE, None, skipped="empty-reference",
            note=rb.JUDGE_EMPTY_REFERENCE_NOTE,
        ),
        _v_grade("t4", _REGRADE_CANDIDATE, None, skipped="cost-ceiling"),
        _v_grade("t5", _REGRADE_CANDIDATE, None, skipped="cost-ceiling"),
    ]
    if not skipped_cell:
        # The "everything finishable" shape: t4's grade becomes pending too.
        pass
    results = {
        "store_schema_version": rb.STORE_SCHEMA_VERSION,
        "run_id": run_id,
        "repo": "/nonexistent/target",
        "base_commit": "0" * 40,
        "mode": "issue-replay",
        "harness": "stub-harness",
        "candidates": list(candidates),
        "judge": judge,
        "cells": cells,
        "grades": grades,
        "spend": spend or {"ceiling_usd": 1.0, "spent_usd": 0.75, "basis": "actual"},
        "labels": [rb.SPEND_BASIS_LABELS["actual"], rb.COST_CEILING_LABEL],
        "notes": ["cost ceiling reached before grading every cell"],
    }
    if verdict is not None:
        results["verdict"] = verdict
    (run_dir / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    if write_tasks:
        for task_id in ("t1", "t2", "t4", "t5"):
            task = _regrade_task(task_id)
            (run_dir / "tasks" / f"{task_id}.json").write_text(json.dumps(task, indent=2) + "\n")
        empty = _regrade_task("t3", reference=_REGRADE_EMPTY_REFERENCE)
        (run_dir / "tasks" / "t3.json").write_text(json.dumps(empty, indent=2) + "\n")
    return store, run_id, run_dir


def _regrade_args(run_id, store, *extra):
    return rb.build_parser().parse_args([
        "regrade", "--run", str(run_id), "--store-dir", str(store), *extra,
    ])


def _run_dir_bytes(root):
    """Every file under a RUN dir -> `{relative path: bytes}`. Byte-identity, not "looks the
    same". Deliberately NOT named `_tree_snapshot` — that name is already taken by the
    fixture-repo helper at the top of this module, and shadowing it silently rewires the
    sandbox and read-only-target tests that depend on it."""
    root = Path(root)
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


class RegradeSpendGateTests(unittest.TestCase):
    """T21 item 1 — the gate is `run`'s, enforced in `run`'s order, and it never spends."""

    def test_missing_either_flag_refuses_and_never_reaches_the_runner(self):
        for extra in ([], ["--live"], ["--max-usd", "5.0"]):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as td:
                store, run_id, run_dir = _write_stranded_run(td)
                before = (run_dir / "results.json").read_bytes()
                runner = _judge_stub_runner()
                args = _regrade_args(run_id, store, *extra)
                with contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()) as err, \
                        self.assertRaises(SystemExit) as ctx:
                    rb.cmd_regrade(args, runner=runner, adapter=_regrade_adapter())
                self.assertEqual(ctx.exception.code, 2)
                self.assertIn("--live", err.getvalue())
                self.assertIn("--max-usd", err.getvalue())
                self.assertEqual(runner.calls, [], "a refusal path reached the runner")
                self.assertEqual((run_dir / "results.json").read_bytes(), before)

    def test_the_cli_refusal_names_both_flags_on_stderr(self):
        # The exact property the T21 verify probe asserts, held here too so a change to the
        # wording fails in the suite rather than only in a shell block.
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _write_stranded_run(td)
            args = _regrade_args(run_id, store)
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()) as err, \
                    self.assertRaises(SystemExit):
                rb.cmd_regrade(args, runner=_explode_runner, adapter=_regrade_adapter())
            self.assertIn("--live", err.getvalue())
            self.assertIn("--max-usd", err.getvalue())

    def test_a_malformed_ceiling_never_reaches_the_dispatch_loop(self):
        for bad in ("nan", "inf", "-inf", "-1"):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as td:
                store, run_id, run_dir = _write_stranded_run(td)
                before = (run_dir / "results.json").read_bytes()
                runner = _judge_stub_runner()
                args = rb.build_parser().parse_args([
                    "regrade", "--run", str(run_id), "--store-dir", str(store), "--live",
                    f"--max-usd={bad}",
                ])
                with contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()) as err, \
                        self.assertRaises(SystemExit) as ctx:
                    rb.cmd_regrade(args, runner=runner, adapter=_regrade_adapter())
                self.assertEqual(ctx.exception.code, 2)
                self.assertIn("finite", err.getvalue())
                self.assertEqual(runner.calls, [], f"--max-usd {bad} reached the runner")
                self.assertEqual((run_dir / "results.json").read_bytes(), before)

    def test_the_ceiling_is_validated_before_the_store_is_even_opened(self):
        # Order matters: a malformed ceiling must refuse for the CEILING's reason, not die on
        # a run id it should never have looked up. This fails the moment the store read moves
        # above `validate_ceiling`.
        with tempfile.TemporaryDirectory() as td:
            args = rb.build_parser().parse_args([
                "regrade", "--run", "no-such-run", "--store-dir", str(Path(td) / "store"),
                "--live", "--max-usd=nan",
            ])
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()) as err, \
                    self.assertRaises(SystemExit) as ctx:
                rb.cmd_regrade(args, runner=_explode_runner, adapter=_regrade_adapter())
            self.assertEqual(ctx.exception.code, 2)
            self.assertIn("finite", err.getvalue())

    def test_the_per_dispatch_ceiling_check_is_the_shared_helper_not_a_copy(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, _ = _write_stranded_run(td)
            args = _regrade_args(run_id, store, "--live", "--max-usd", "100")
            with mock.patch.object(
                rb, "would_exceed_ceiling", wraps=rb.would_exceed_ceiling
            ) as ceiling_spy, mock.patch.object(
                rb, "validate_ceiling", wraps=rb.validate_ceiling
            ) as validate_spy:
                with contextlib.redirect_stdout(io.StringIO()):
                    rb.cmd_regrade(
                        args, runner=_judge_stub_runner(), adapter=_regrade_adapter()
                    )
            self.assertGreaterEqual(
                ceiling_spy.call_count, 2,
                "every judge grade must be ceiling-checked BEFORE it is dispatched",
            )
            # once for the CLI gate + once inside every `would_exceed_ceiling`
            self.assertGreaterEqual(validate_spy.call_count, 3, validate_spy.call_args_list)

    def test_the_ceiling_is_fresh_not_a_continuation_of_the_old_runs_arithmetic(self):
        # The stranded run already recorded $0.75 against a $1.00 ceiling. A regrade under a
        # ceiling SMALLER than that recorded spend must still dispatch: its budget starts at
        # $0.00. If the old spend were carried in, nothing would ever be regradeable.
        with tempfile.TemporaryDirectory() as td:
            store, run_id, run_dir = _write_stranded_run(td)
            unit = rb.estimate_dispatch_usd(
                _REGRADE_JUDGE, rb.JUDGE_GRADE_PROFILE, FIXTURE_PRICING
            )
            self.assertLess(unit * 2, 0.75, "fixture pricing no longer makes this test sharp")
            runner = _judge_stub_runner()
            args = _regrade_args(run_id, store, "--live", "--max-usd", str(unit * 2.5))
            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_regrade(args, runner=runner, adapter=_regrade_adapter())
            self.assertEqual(len(runner.calls), 2)
            results = json.loads((run_dir / "results.json").read_text())
            self.assertAlmostEqual(results["regrades"][0]["spent_usd"], unit * 2)


class RegradeTouchesOnlyStrandedGradesTests(unittest.TestCase):
    """T21 item 2 — completed work is PROVABLY untouched, not merely un-mentioned."""

    def _regrade(self, td, *extra, runner=None):
        store, run_id, run_dir = _write_stranded_run(td)
        before = json.loads((run_dir / "results.json").read_text())
        runner = runner or _judge_stub_runner()
        args = _regrade_args(run_id, store, "--live", "--max-usd", "100", *extra)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = rb.cmd_regrade(args, runner=runner, adapter=_regrade_adapter())
        after = json.loads((run_dir / "results.json").read_text())
        return rc, before, after, runner, out.getvalue(), run_dir, store

    def test_only_the_cost_ceiling_skips_with_a_dispatched_cell_are_re_dispatched(self):
        with tempfile.TemporaryDirectory() as td:
            rc, before, after, runner, text, _, _ = self._regrade(td)
            self.assertEqual(rc, 0)
            self.assertEqual(len(runner.calls), 2, "exactly the two pending grades")

            # the COMPLETED grade, byte for byte
            self.assertEqual(
                json.dumps(after["grades"][0]), json.dumps(before["grades"][0]),
                "a completed judge grade was rewritten",
            )
            # the EMPTY-REFERENCE skip: not a budget casualty, never re-dispatched (T7R law)
            self.assertEqual(
                json.dumps(after["grades"][2]), json.dumps(before["grades"][2]),
                "an empty-reference skip was touched",
            )
            self.assertEqual(after["grades"][2]["skipped"], "empty-reference")
            # the unfinishable cost-ceiling skip (its cell never ran)
            self.assertEqual(
                json.dumps(after["grades"][3]), json.dumps(before["grades"][3]),
                "a grade whose candidate cell never ran was touched",
            )
            # the two PENDING grades are now real
            for index in (1, 4):
                self.assertIsNone(after["grades"][index]["skipped"])
                self.assertIsNotNone(after["grades"][index]["grade"])
                self.assertEqual(after["grades"][index]["judge_model"], _REGRADE_JUDGE)

    def test_candidate_cells_are_never_re_dispatched(self):
        with tempfile.TemporaryDirectory() as td:
            _, before, after, runner, _, _, _ = self._regrade(td)
            self.assertEqual(
                json.dumps(after["cells"]), json.dumps(before["cells"]),
                "regrade rewrote a candidate cell",
            )
            for call in runner.calls:
                argv = call["argv"]
                self.assertEqual(
                    argv[argv.index("--model") + 1], _REGRADE_JUDGE,
                    "a regrade dispatch went to a CANDIDATE model",
                )

    def test_nothing_is_reordered_dropped_or_appended(self):
        with tempfile.TemporaryDirectory() as td:
            _, before, after, _, _, _, _ = self._regrade(td)
            self.assertEqual(
                [(g["task_id"], g["candidate_model"]) for g in after["grades"]],
                [(g["task_id"], g["candidate_model"]) for g in before["grades"]],
                "the grades list was reordered or resized",
            )

    def test_the_judge_disciplines_are_grade_cells_and_are_not_re_derived(self):
        source = inspect.getsource(rb.cmd_regrade)
        self.assertIn("grade_cells(", source)
        for forbidden in (
            "oracle_judge(", "build_judge_prompt(", "parse_judge_output(",
            "_strip_test_hunks(", "would_exceed_ceiling(", "math.isfinite",
            "secrets.randbelow",
        ):
            self.assertNotIn(
                forbidden, source,
                f"cmd_regrade re-derives {forbidden} instead of reusing grade_cells",
            )
        self.assertIn("validate_ceiling(", source)

    def test_the_blind_slot_audit_record_survives_and_the_reference_is_stripped(self):
        with tempfile.TemporaryDirectory() as td:
            runner = _judge_stub_runner()
            _, _, after, _, _, _, _ = self._regrade(td, "--judge-seed", "1", runner=runner)
            for index in (1, 4):
                grade = after["grades"][index]
                self.assertEqual(grade["slots"], {"A": "reference", "B": "candidate"})
                self.assertEqual(grade["grade"]["slots"], grade["slots"])
            # F4c / P1-F5: whatever reaches a judge prompt has been through the same
            # `_strip_test_hunks` `grade_cells` applies — no test-path hunk in any prompt.
            for call in runner.calls:
                self.assertNotIn("tests/test_a.py", call["argv"][-1])

    def test_slots_are_re_randomized_per_grade_by_default(self):
        # PLAN D6, and NOT a formality: this property surfaced as a genuinely non-deterministic
        # test result before `--judge-seed` was pinned in the verdict test below. Omitting the
        # flag must keep the per-grade randomization `oracle_judge` performs — the seed is an
        # opt-in reproducibility escape hatch, never the default.
        with tempfile.TemporaryDirectory() as td:
            store, run_id, run_dir = _write_stranded_run(td)
            args = _regrade_args(run_id, store, "--live", "--max-usd", "100")
            with mock.patch.object(rb.secrets, "randbelow", side_effect=[0, 1]) as spy:
                with contextlib.redirect_stdout(io.StringIO()):
                    rb.cmd_regrade(
                        args, runner=_judge_stub_runner(), adapter=_regrade_adapter()
                    )
            self.assertEqual(spy.call_count, 2, "the slot seed was not drawn per grade")
            results = json.loads((run_dir / "results.json").read_text())
            self.assertEqual(results["grades"][1]["slots"], {"A": "candidate", "B": "reference"})
            self.assertEqual(results["grades"][4]["slots"], {"A": "reference", "B": "candidate"})

    def test_the_judge_cwd_stays_outside_the_run_dir_and_the_store(self):
        with tempfile.TemporaryDirectory() as td:
            _, _, _, runner, _, run_dir, store = self._regrade(td)
            self.assertTrue(runner.calls)
            for call in runner.calls:
                cwd = Path(call["cwd"]).resolve()
                self.assertNotEqual(cwd, run_dir.resolve())
                self.assertNotIn(run_dir.resolve(), cwd.parents)
                self.assertNotIn(Path(store).resolve(), cwd.parents)

    def test_results_json_is_the_only_file_a_regrade_writes(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, run_dir = _write_stranded_run(td)
            before = _run_dir_bytes(run_dir)
            args = _regrade_args(run_id, store, "--live", "--max-usd", "100")
            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_regrade(args, runner=_judge_stub_runner(), adapter=_regrade_adapter())
            after = _run_dir_bytes(run_dir)
            self.assertEqual(
                sorted(before), sorted(after), "a regrade added or removed a store file"
            )
            changed = [name for name in before if before[name] != after[name]]
            self.assertEqual(changed, ["results.json"], changed)

    def test_a_judge_that_is_also_a_candidate_refuses_before_any_dispatch(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, run_dir = _write_stranded_run(
                td, judge=_REGRADE_CANDIDATE, candidates=(_REGRADE_CANDIDATE,)
            )
            before = (run_dir / "results.json").read_bytes()
            runner = _judge_stub_runner()
            args = _regrade_args(run_id, store, "--live", "--max-usd", "100")
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()) as err, \
                    self.assertRaises(SystemExit) as ctx:
                rb.cmd_regrade(args, runner=runner, adapter=_regrade_adapter())
            self.assertEqual(ctx.exception.code, 2)
            self.assertIn("hard refusal", err.getvalue())
            self.assertEqual(runner.calls, [])
            self.assertEqual((run_dir / "results.json").read_bytes(), before)

    def test_the_judge_candidate_refusal_reads_the_cells_not_just_the_declared_list(self):
        # `build_verdict` already treats a cell naming an undeclared model as a candidate. A
        # refusal that trusted `candidates` alone would fail OPEN on that envelope and let a
        # model grade its own patch — the exact fail-open shape this kit found four times.
        with tempfile.TemporaryDirectory() as td:
            store, run_id, run_dir = _write_stranded_run(
                td, judge=_REGRADE_CANDIDATE, candidates=(),
            )
            before = (run_dir / "results.json").read_bytes()
            runner = _judge_stub_runner()
            args = _regrade_args(run_id, store, "--live", "--max-usd", "100")
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()) as err, \
                    self.assertRaises(SystemExit) as ctx:
                rb.cmd_regrade(args, runner=runner, adapter=_regrade_adapter())
            self.assertEqual(ctx.exception.code, 2)
            self.assertIn("hard refusal", err.getvalue())
            self.assertEqual(runner.calls, [])
            self.assertEqual((run_dir / "results.json").read_bytes(), before)

    def test_a_missing_task_record_leaves_its_grade_skipped_rather_than_guessing(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, run_dir = _write_stranded_run(td)
            (run_dir / "tasks" / "t5.json").unlink()
            before = json.loads((run_dir / "results.json").read_text())
            runner = _judge_stub_runner()
            args = _regrade_args(run_id, store, "--live", "--max-usd", "100")
            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_regrade(args, runner=runner, adapter=_regrade_adapter())
            after = json.loads((run_dir / "results.json").read_text())
            self.assertEqual(len(runner.calls), 1, "only t2 remained finishable")
            self.assertEqual(
                json.dumps(after["grades"][4]), json.dumps(before["grades"][4])
            )
            self.assertTrue(
                any(rb.REGRADE_TASK_RECORD_MISSING_NOTE in n for n in after["notes"]),
                after["notes"],
            )


class RegradeEnvelopeHonestyTests(unittest.TestCase):
    """T21 item 4 — one envelope, two invocations, and no blurred number between them."""

    def _regrade(self, run_id, store, *extra, runner=None, adapter=None):
        runner = runner or _judge_stub_runner()
        args = _regrade_args(run_id, store, *extra)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = rb.cmd_regrade(args, runner=runner, adapter=adapter or _regrade_adapter())
        return rc, runner, out.getvalue()

    def test_a_regrades_entry_records_this_invocation(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, run_dir = _write_stranded_run(td)
            self._regrade(run_id, store, "--live", "--max-usd", "100")
            results = json.loads((run_dir / "results.json").read_text())
            self.assertEqual(len(results["regrades"]), 1)
            entry = results["regrades"][0]
            self.assertTrue(RUN_ID_RE.match(entry["invocation_id"]), entry["invocation_id"])
            self.assertAlmostEqual(entry["ceiling_usd"], 100.0)
            self.assertEqual(entry["grades_dispatched"], 2)
            self.assertEqual(entry["grades_skipped_cost_ceiling"], 0)
            # t4 alone: an `empty-reference` skip is not a cost-ceiling skip at all and is
            # never counted as a budget casualty (T7R).
            self.assertEqual(entry["grades_unfinishable"], 1)
            self.assertEqual(entry["judge"], _REGRADE_JUDGE)
            self.assertFalse(entry["stopped"])
            self.assertIn(entry["basis"], rb.SPEND_BASIS_LABELS)
            self.assertIn(rb.REGRADE_LABEL, results["labels"])

    def test_spend_is_reported_per_invocation_and_never_summed(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, run_dir = _write_stranded_run(td)
            before = json.loads((run_dir / "results.json").read_text())
            self._regrade(run_id, store, "--live", "--max-usd", "100")
            after = json.loads((run_dir / "results.json").read_text())

            # the ORIGINAL run's spend record is not inflated to absorb regrade dollars —
            # that inflation is exactly the blur a single mixed number would be.
            self.assertEqual(json.dumps(after["spend"]), json.dumps(before["spend"]))
            rows = after["spend_by_invocation"]
            self.assertEqual([r["kind"] for r in rows], ["run", "regrade"])
            self.assertEqual(rows[0]["invocation"], run_id)
            self.assertAlmostEqual(rows[0]["spent_usd"], before["spend"]["spent_usd"])
            self.assertEqual(rows[0]["basis"], "actual")
            # the stub reports no token counts, so this invocation is honestly `estimated`:
            # two DIFFERENT bases, side by side, which is the whole point.
            self.assertEqual(rows[1]["basis"], "estimated")
            for row in rows:
                self.assertIsNotNone(row["basis"], "a dollar figure with no basis")
            for forbidden in ("total_usd", "combined_usd", "spent_total_usd"):
                self.assertNotIn(forbidden, after)

    def test_list_says_the_run_spend_cell_is_not_the_whole_bill_after_a_regrade(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, run_dir = _write_stranded_run(td)
            before_rows, _ = rb.list_runs(store)
            self.assertEqual(before_rows[0]["regrades"], 0)

            self._regrade(run_id, store, "--live", "--max-usd", "100")

            rows, _ = rb.list_runs(store)
            self.assertEqual(rows[0]["regrades"], 1)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rb.main(["list", "--store-dir", str(store), "--prefs-path",
                         str(Path(td) / "no-such-prefs.json")])
            self.assertIn("regrades: 1", out.getvalue())

    def test_the_cost_ceiling_label_is_retained_while_any_cost_ceiling_skip_remains(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, run_dir = _write_stranded_run(td)  # t4's CELL is skipped
            self._regrade(run_id, store, "--live", "--max-usd", "100")
            results = json.loads((run_dir / "results.json").read_text())
            self.assertIn(
                rb.COST_CEILING_LABEL, results["labels"],
                "the partial label came off while a cost-ceiling skip remained",
            )
            self.assertFalse(
                any(rb.COST_CEILING_CLEARED_NOTE in n for n in results["notes"])
            )

    def test_the_cost_ceiling_label_comes_off_only_when_nothing_is_left_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, run_dir = _write_stranded_run(td, skipped_cell=False)
            self._regrade(run_id, store, "--live", "--max-usd", "100")
            results = json.loads((run_dir / "results.json").read_text())
            self.assertNotIn(rb.COST_CEILING_LABEL, results["labels"])
            self.assertTrue(any(rb.COST_CEILING_CLEARED_NOTE in n for n in results["notes"]))
            self.assertFalse(
                [g for g in results["grades"] if g.get("skipped") == "cost-ceiling"]
            )

    def test_a_note_names_what_this_regrade_finished(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, run_dir = _write_stranded_run(td)
            _, _, text = self._regrade(run_id, store, "--live", "--max-usd", "100")
            results = json.loads((run_dir / "results.json").read_text())
            invocation = results["regrades"][0]["invocation_id"]
            self.assertTrue(
                any(f"regrade {invocation}: finished 2 of 2" in n for n in results["notes"]),
                results["notes"],
            )
            self.assertIn("completed: 2 judge grade(s) dispatched", text)

    def test_a_mid_regrade_ceiling_stop_is_honest_and_resumable(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, run_dir = _write_stranded_run(td, skipped_cell=False)
            unit = rb.estimate_dispatch_usd(
                _REGRADE_JUDGE, rb.JUDGE_GRADE_PROFILE, FIXTURE_PRICING
            )
            # room for exactly one of the three pending grades
            runner = _judge_stub_runner()
            _, _, text = self._regrade(
                run_id, store, "--live", "--max-usd", str(unit * 1.5), runner=runner
            )
            self.assertEqual(len(runner.calls), 1)
            self.assertIn("STOPPED: cost ceiling reached", text)
            self.assertIn("resumable", text)

            first = json.loads((run_dir / "results.json").read_text())
            self.assertTrue(first["regrades"][0]["stopped"])
            self.assertEqual(first["regrades"][0]["grades_dispatched"], 1)
            self.assertEqual(first["regrades"][0]["grades_skipped_cost_ceiling"], 2)
            self.assertIn(rb.COST_CEILING_LABEL, first["labels"])
            self.assertAlmostEqual(first["regrades"][0]["spent_usd"], unit)

            # …and it is genuinely resumable: a second, larger ceiling finishes the rest.
            runner2 = _judge_stub_runner()
            self._regrade(run_id, store, "--live", "--max-usd", "100", runner=runner2)
            second = json.loads((run_dir / "results.json").read_text())
            self.assertEqual(len(runner2.calls), 2)
            self.assertEqual(len(second["regrades"]), 2)
            self.assertEqual(
                [r["kind"] for r in second["spend_by_invocation"]],
                ["run", "regrade", "regrade"],
            )
            self.assertNotIn(rb.COST_CEILING_LABEL, second["labels"])
            self.assertFalse(
                [g for g in second["grades"] if g.get("skipped") == "cost-ceiling"]
            )
            # the grade the FIRST regrade landed is itself now finished work
            self.assertEqual(
                json.dumps(second["grades"][1]), json.dumps(first["grades"][1])
            )

    def test_a_second_regrade_with_nothing_to_do_changes_nothing_and_says_so(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, run_dir = _write_stranded_run(td)
            self._regrade(run_id, store, "--live", "--max-usd", "100")
            settled = (run_dir / "results.json").read_bytes()

            runner = _judge_stub_runner()
            rc, _, text = self._regrade(
                run_id, store, "--live", "--max-usd", "100", runner=runner
            )
            self.assertEqual(rc, 0)
            self.assertEqual(runner.calls, [], "an idempotent regrade dispatched anyway")
            self.assertIn(rb.REGRADE_NOTHING_PENDING_NOTE, text)
            self.assertEqual(
                (run_dir / "results.json").read_bytes(), settled,
                "a no-op regrade rewrote the envelope",
            )

    def test_a_grading_failure_still_records_the_dollars_already_spent(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, run_dir = _write_stranded_run(td)
            calls = []

            def runner(argv, cwd):
                calls.append(argv)
                if len(calls) > 1:
                    raise RuntimeError("the harness vanished mid-pass")
                return 0, _canned_result_json(None) + "\nGRADE A=correct B=partial EQUIVALENT=no"

            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_regrade(
                    _regrade_args(run_id, store, "--live", "--max-usd", "100"),
                    runner=runner, adapter=_regrade_adapter(),
                )
            results = json.loads((run_dir / "results.json").read_text())
            self.assertIn(rb.GRADING_FAILED_LABEL, results["labels"])
            self.assertGreater(results["regrades"][0]["spent_usd"], 0.0)
            self.assertIsNone(results["grades"][1]["skipped"], "the landed grade was lost")
            self.assertEqual(results["grades"][4]["skipped"], "cost-ceiling")


class RegradeVerdictPickupTests(unittest.TestCase):
    """T21 item 5 — `verdict` reads the envelope, so it picks the merged grades up with no
    code change of its own. Asserted, not asserted-about."""

    def test_the_verdict_picks_up_merged_grades_with_no_code_change(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, run_dir = _write_stranded_run(td)
            before = _verdict(run_dir, pricing=FIXTURE_PRICING)
            row_before = _rows_by(before, "t2", _REGRADE_CANDIDATE)
            self.assertEqual(row_before["judge"]["skipped"], "cost-ceiling")
            self.assertIsNone(row_before["judge"]["grade"])

            # `--judge-seed 0` pins the candidate into slot A so the stub's
            # `A=correct B=partial` is deterministic. Without it the slot assignment is
            # re-randomized per grade, which is PLAN D6's bias control and is asserted
            # directly in `test_slots_are_re_randomized_per_grade_by_default` below.
            args = _regrade_args(run_id, store, "--live", "--max-usd", "100",
                                 "--judge-seed", "0")
            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_regrade(args, runner=_judge_stub_runner(), adapter=_regrade_adapter())

            after = _verdict(run_dir, pricing=FIXTURE_PRICING)
            row_after = _rows_by(after, "t2", _REGRADE_CANDIDATE)
            self.assertIsNone(row_after["judge"]["skipped"])
            self.assertEqual(row_after["judge"]["grade"], "correct")
            # t3's empty-reference skip is still exactly that in the verdict — a design
            # decision, never re-attributed to the budget.
            self.assertEqual(
                _rows_by(after, "t3", _REGRADE_CANDIDATE)["judge"]["skipped"],
                "empty-reference",
            )

    def test_the_verdict_renders_the_per_invocation_spend_lines(self):
        with tempfile.TemporaryDirectory() as td:
            store, run_id, run_dir = _write_stranded_run(td)
            plain = rb.render_verdict_markdown(_verdict(run_dir, pricing=FIXTURE_PRICING))
            self.assertNotIn(rb.SPEND_PER_INVOCATION_NOTE, plain)

            args = _regrade_args(run_id, store, "--live", "--max-usd", "100")
            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_regrade(args, runner=_judge_stub_runner(), adapter=_regrade_adapter())

            card = _verdict(run_dir, pricing=FIXTURE_PRICING)
            markdown = rb.render_verdict_markdown(card)
            self.assertIn(rb.SPEND_PER_INVOCATION_NOTE, markdown)
            self.assertIn(f"run {run_id}:", markdown)
            self.assertIn("regrade ", markdown)
            self.assertIn(rb.REGRADE_LABEL, card["labels"])

    def test_a_verdict_folded_in_before_a_regrade_is_stamped_stale_and_apply_refuses_it(self):
        with tempfile.TemporaryDirectory() as td:
            verdict = {
                "verdict_schema_version": rb.VERDICT_SCHEMA_VERSION,
                "goal": "both",
                "min_tasks": rb.MIN_EVIDENCE_TASKS,
                "below_floor": False,
                "below_floor_label": None,
                "rule": "synthetic rule text",
                "capability_order": [],
                "tier_map": {
                    "slots": {"strong": "fake-opus-1", "mid": "fake-sonnet-1", "weak": None},
                    "nearest_neighbors": {}, "role_gloss": {}, "notes": [],
                },
                "daily_driver": {"pick": "fake-haiku-1", "notes": []},
                "three_legs": [], "disagreements": [], "labels": [], "notes": [],
            }
            store, run_id, run_dir = _write_stranded_run(td, verdict=verdict)
            prefs = Path(td) / "prefs.json"

            # …applicable BEFORE the regrade
            payload, _ = rb.apply_verdict(run_dir, prefs, FIXTURE_PRICING)
            self.assertEqual(payload["tiers"]["strong"], "fake-opus-1")

            args = _regrade_args(run_id, store, "--live", "--max-usd", "100")
            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_regrade(args, runner=_judge_stub_runner(), adapter=_regrade_adapter())

            results = json.loads((run_dir / "results.json").read_text())
            self.assertIs(results["verdict"]["stale_after_regrade"], True)
            self.assertEqual(
                results["verdict"]["labels"][0], rb.VERDICT_STALE_AFTER_REGRADE_LABEL
            )
            with self.assertRaises(ValueError) as ctx:
                rb.apply_verdict(run_dir, prefs, FIXTURE_PRICING)
            self.assertIn("regrade", str(ctx.exception))

            # and one re-render clears it
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                rb.cmd_verdict(rb.build_parser().parse_args([
                    "verdict", "--run", str(run_id), "--store-dir", str(store),
                ]))
            refreshed = json.loads((run_dir / "results.json").read_text())
            self.assertNotIn("stale_after_regrade", refreshed["verdict"])


class RegradeOnARealStubbedRunTests(unittest.TestCase):
    """End to end on a REAL stubbed run: a `run` whose ceiling bit during the grading pass,
    finished by a `regrade`. Fixture git repo, injected runners, temp store — no spend."""

    def test_a_run_stranded_mid_grading_is_finished_by_a_regrade(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            repo = td / "target"
            build_issue_fixture_repo(repo)
            store = td / "store"

            card = rb.build_plan(repo, ["haiku"], scratch_dir=td / "plan-scratch")
            judge_id = card["judge"]
            self.assertGreaterEqual(len(card["tasks"]), 2)

            def run_runner(argv, cwd):
                (Path(cwd) / "candidate_fix.py").write_text("# cheap candidate work\n")
                model = argv[argv.index("--model") + 1]
                if model == judge_id:
                    payload = {
                        "type": "result", "subtype": "success",
                        "usage": {"input_tokens": 10_000_000_000, "output_tokens": 1},
                    }
                    return 0, json.dumps(payload) + "\nGRADE A=correct B=correct EQUIVALENT=yes"
                return 0, _canned_result_json({"input_tokens": 10, "output_tokens": 5})

            with contextlib.redirect_stdout(io.StringIO()):
                rb.cmd_run(
                    _run_args(repo, store, "--live", "--max-usd",
                              str(card["totals"]["grand_total"] + 0.01)),
                    runner=run_runner,
                )

            run_id = rb.list_runs(store)[0][0]["run_id"]
            run_dir = store / run_id
            before = json.loads((run_dir / "results.json").read_text())
            stranded = [g for g in before["grades"] if g.get("skipped") == "cost-ceiling"]
            self.assertTrue(stranded, "the fixture run did not strand a judge grade")
            self.assertTrue(all(not c["skipped"] for c in before["cells"]))

            regrade_runner = _judge_stub_runner(
                output="GRADE A=partial B=correct EQUIVALENT=no",
                usage={"input_tokens": 10, "output_tokens": 5},
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = rb.cmd_regrade(
                    _regrade_args(run_id, store, "--live", "--max-usd", "100"),
                    runner=regrade_runner,
                )
            self.assertEqual(rc, 0)
            self.assertEqual(len(regrade_runner.calls), len(stranded))

            after = json.loads((run_dir / "results.json").read_text())
            self.assertEqual(json.dumps(after["cells"]), json.dumps(before["cells"]))
            self.assertFalse(
                [g for g in after["grades"] if g.get("skipped") == "cost-ceiling"]
            )
            self.assertNotIn(rb.COST_CEILING_LABEL, after["labels"])
            self.assertIn(rb.REGRADE_LABEL, after["labels"])
            self.assertEqual(after["regrades"][0]["grades_dispatched"], len(stranded))
            # the target repo is still read-only by construction: a regrade never touches it
            self.assertEqual(
                subprocess.run(
                    ["git", "-C", str(repo), "status", "--porcelain"],
                    capture_output=True, text=True,
                ).stdout,
                "",
            )


if __name__ == "__main__":
    unittest.main()
