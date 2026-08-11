# TASKS — repo-bench

Repo root: `/path/to/polytropos`. Run every verify command from
there. Read `PLAN.md` and `GUARDRAILS.md` (same directory) first — D1–D11 and the
OUT-OF-SCOPE fence are binding.
Status vocabulary: `pending | in-progress | done | blocked`.

Dispatch notes for the orchestrator: pass each task's `model` as the Agent tool's `model`
parameter when dispatching `repo-bench-implementer`. **Warm-cluster hints:** T2 → T3 are
strictly serial on `bin/repo_bench.py` with the same `sonnet` pin — one warm implementer may
serve both. T6 → T7 likewise (serial, same file, both `sonnet`). T1, T5, T8 are lone `opus`
pins — always fresh. T10, T11, T12 are `independent:` with disjoint files — fresh parallel
fan-out in one message. Everything else is serial by `depends:`.

Standing rules for every task:

- Stdlib only; unittest via `python3 -m unittest discover -s tests [-p '<file>.py'] -q`.
- NEVER invoke the real `claude`/`copilot`/`codex`/`gh` CLI from any code path a test or
  verify reaches. Dispatch and `gh` enrichment go through injectable runner callables; every
  test injects a stub. `subprocess` to `git` is sanctioned (local and free), but code paths
  that touch a TARGET repo use only the D3 read-only allowlist.
- Tests build throwaway fixture git repos in temp dirs (`git init` + commits with
  `-c user.name=t -c user.email=t@example.com`; never rely on the default branch name — use
  `rev-parse HEAD`). Never the real `benchruns/`, `prefs/`, or any `~/` dir.
- No prices, price ratios, or real model ids hardcoded — resolve through
  `data/pricing.json` via the reused loaders at run time. Fixture pricing dicts in tests use
  obviously-fake ids (e.g. `fake-strong-1`).
- Reuse, never fork: `bin/claude_execute.py`, `bin/cost_report.py`,
  `bin/routing_scorecard.py`, `bin/bench_routing.py` are loaded via the house importlib
  pattern (`bench_routing._load`, ≈ line 117) and never edited.
- Every verify block ends with the full suite and the layout test — both can fail. Never
  write `producer | python3 - <<'PY'` (pipe and heredoc both claim stdin): redirect producer
  output to a file first, then probe the file.
- Do not commit or push.

## Phase 1 — Acquisition without spend (sandbox, miners — no model, no network, no money)

### T1 — NEW `bin/repo_bench.py`: CLI skeleton, read-only target access, leak-proof sandbox, run store
- status: done
- model: opus
- depends: (none)

**Files:** NEW `bin/repo_bench.py`; NEW `tests/test_repo_bench.py`.

**Why:** everything else hangs off three safety-critical foundations: the target repo is
read-only by construction (D3), the sandbox can never leak the reference fix (D3/R2), and
the store layout is pinned before any writer exists (D8).

**Do:**
1. Module docstring: state the money/network law (real dispatch only behind `--live` +
   `--max-usd`; every dispatch through an injectable runner; tests stub everything), the
   target-repo read-only law, and the store law (`bin/repo_bench.py` is the only writer
   under a benchruns store; never hand-authored, never backdated). Constants:
   `STORE_SCHEMA_VERSION = 1`, `PLUGIN_ROOT = Path(__file__).resolve().parents[1]`,
   `DEFAULT_STORE_DIR = PLUGIN_ROOT / "benchruns"`,
   `READ_ONLY_GIT = ("archive", "show", "log", "rev-parse", "diff", "ls-tree", "cat-file",
   "status")`. Copy the `_load(name)` importlib helper from `bin/bench_routing.py` (≈ line
   117) and lazy-load `claude_execute` as `ce` where needed.
2. `git_target(repo, *args, git_runner=None) -> (rc, output)` — THE single choke point for
   touching a target repo. It asserts `args[0] in READ_ONLY_GIT` (raise `ValueError` naming
   the allowlist otherwise) and runs `["git", "-C", str(repo), *args]` through `git_runner`
   (default: a module-level subprocess runner returning `(rc, stdout+stderr)`). No other
   function in this module may run git against a target path — sandbox-internal git goes
   through a separate plain helper `git_sandbox(sandbox, *args)` with no allowlist (the
   sandbox is ours).
3. `make_sandbox(target_repo, commit, dest, git_runner=None) -> dict` — D3 exactly:
   `git archive <commit>` from the target (via `git_target`, output to a temp tar file, then
   `tarfile` extraction — stdlib, no shell pipes), then in `dest`: `git init`, add-all, one
   initial commit (`-c user.name`/`user.email` pinned), record the initial commit hash.
   Returns `{"path", "base_commit": <target commit>, "init_commit": <sandbox hash>}`. The
   sandbox contains NO target history by construction.
4. `capture_patch(sandbox) -> str` — `git add -A` in the sandbox then diff against the
   recorded initial commit such that untracked new files are included and agent-made commits
   don't hide changes (diff `<init_commit>` → working tree with `--cached` after add, or
   equivalent — pick one, test both cases: uncommitted edits and a committed change).
5. Run store: `new_run_dir(store_dir) -> (run_id, run_path)` using `ce.generate_run_id()`;
   creates `<store>/<run_id>/` with subdirs `tasks/`, `dispatches/`, `work/` and writes
   `plan.json` placeholder-free later (T4) — here just `meta.json` `{store_schema_version,
   run_id, created_at (UTC ISO)}`. `list_runs(store_dir) -> (rows, notes)` — tolerant reader:
   missing dir → `([], ["no benchruns store at <dir> — run a plan first"])`; non-dir or
   undecodable `meta.json` entries → skip + note; never a crash.
6. CLI skeleton (`argparse`, subcommands): `plan`, `run`, `verdict`, `apply`, `list`,
   `demo` — `list` works now; `demo` for now smokes sandbox+capture on a self-built fixture
   repo in a temp dir and prints what it proved; the rest print `not implemented yet` to
   stderr + exit 2 (later tasks replace them). `main(argv=None)` catching
   `ValueError`/`FileNotFoundError`/`KeyError` → stderr + exit 2 (the `claude_execute`
   pattern).
7. NEW `tests/test_repo_bench.py` (importlib load pattern from `tests/test_cost_report.py`):
   fixture-repo builder helper (temp dir, two commits so parent≠HEAD); cover: allowlist —
   `git_target(repo, "checkout", ...)` raises naming the allowlist, `git_target` never
   invoked with a write verb anywhere (grep the module source for `"checkout"`, `"reset"`,
   `"clean"`, `"push"` as git_target args is impractical — instead assert the constant's
   exact membership and that `make_sandbox` calls only `git_target`/`git_sandbox`);
   sandbox — `dest` tree equals the archive of `commit`, `git -C dest log --oneline` shows
   exactly ONE commit, and the fixture's HEAD/refs and `status --porcelain` are unchanged
   after sandboxing; capture — both the uncommitted and the committed-change case yield a
   patch containing the new file; store — `new_run_dir` id matches
   `^\d{4}-\d{2}-\d{2}-[0-9a-f]{4}$`, `list_runs` tolerance matrix (missing dir, rogue
   file, undecodable meta).

**Acceptance:** the module imports clean; target access has exactly one choke point with an
enforced allowlist; sandbox has no history; store reader degrades with notes; all new tests
green; no edit to any reused module.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest discover -s tests -p 'test_repo_bench.py' -q
python3 bin/repo_bench.py demo > /tmp/repo_bench_t1_demo.txt
grep -qi "sandbox" /tmp/repo_bench_t1_demo.txt
python3 - <<'PY'
import importlib.util, subprocess, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location("repo_bench", "bin/repo_bench.py")
rb = importlib.util.module_from_spec(spec); spec.loader.exec_module(rb)
assert rb.READ_ONLY_GIT and "archive" in rb.READ_ONLY_GIT and "checkout" not in rb.READ_ONLY_GIT
with tempfile.TemporaryDirectory() as td:
    td = Path(td); repo = td / "fix"; repo.mkdir()
    def g(*a): subprocess.run(["git", "-C", str(repo), "-c", "user.name=t",
        "-c", "user.email=t@example.com", *a], check=True, capture_output=True)
    g("init"); (repo / "a.txt").write_text("one\n"); g("add", "-A"); g("commit", "-m", "c1")
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True).stdout.strip()
    sb = rb.make_sandbox(repo, head, td / "sb")
    n = subprocess.run(["git", "-C", str(td / "sb"), "rev-list", "--count", "HEAD"],
        capture_output=True, text=True, check=True).stdout.strip()
    assert n == "1", f"sandbox history leaked: {n} commits"
    st = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True, text=True, check=True).stdout
    assert st == "", f"target repo mutated: {st!r}"
    try:
        rb.git_target(repo, "checkout", head)
        raise AssertionError("write verb accepted by git_target")
    except ValueError as e:
        assert "archive" in str(e)
print("T1 probe OK")
PY
git diff --quiet bin/claude_execute.py bin/cost_report.py bin/routing_scorecard.py bin/bench_routing.py
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T2 — Issue-replay miner: fix-commit pairs, test blobs, leak-proof prompts
- status: done
- model: sonnet
- depends: T1

**Files:** `bin/repo_bench.py`; `tests/test_repo_bench.py` (extend).

**Why:** mode A (D4) — the highest-fidelity task source: the repo's own closed issues with
real reference fixes.

**Do:**
1. `DEFAULT_TEST_PATTERNS = ("tests/", "test/", "spec/", "test_", "_test.", ".spec.")` —
   path-substring patterns; a diff path matches when any pattern is a substring of it (or a
   leading dir). `ISSUE_REF_RE` matching (case-insensitive)
   `(fix(e[sd])?|close[sd]?|resolve[sd]?)\s+#(\d+)` plus squash-merge subjects ending
   `(#N)`.
2. `mine_issue_tasks(target_repo, limit=8, test_patterns=DEFAULT_TEST_PATTERNS,
   git_runner=None, gh_runner=None) -> (tasks, notes)`. Via `git_target` only: walk
   `log --no-merges --format=...` newest-first; for each commit whose message matches
   `ISSUE_REF_RE`: base = first parent (`rev-parse <sha>^`; a root commit → skip + note);
   reference patch = `diff <base> <sha>`; touched paths = `diff --name-only`; test paths =
   those matching patterns; `oracle_tests_available` = bool(test paths); `test_blobs` =
   `{path: show <sha>:<path>}` for each test path (extracted NOW — the sandbox has no
   history later). Statement: if `gh_runner` is provided AND the caller passed
   `--with-gh` semantics (parameter `use_gh=False` default), call it with
   `["gh", "issue", "view", N, ...]` and use title/body, `statement_source: "issue"`; else
   commit subject+body, `statement_source: "commit-message"` + label
   `"statement from commit message (weaker than issue text)"`. `gh_runner` has NO subprocess
   default — `use_gh` without a runner wired by the CLI is the only path to a real `gh`, and
   tests never take it.
3. Task record schema (pinned — later tasks consume it): `{"task_id": "issue-<N>-<sha7>",
   "mode": "issue-replay", "issue": N|None, "base_commit", "fix_commit", "subject",
   "statement", "statement_source", "reference_patch", "test_blobs": {...},
   "oracle_tests_available": bool, "size_profile", "labels": [...], "notes": [...]}`.
   `size_profile` maps changed-LOC of the reference patch to a `data/pricing.json`
   `task_profiles` key via pinned thresholds `SIZE_THRESHOLDS = ((10, "XS"), (60, "S"),
   (250, "M"))`, else `"L"` — profile KEYS are data-driven (assert they exist in the loaded
   pricing dict at plan time), thresholds are structural.
4. `build_prompt(task) -> str`: statement + explicit instructions (work only inside the
   current directory; make the change; run nothing that needs a network; do not ask
   questions). THE LEAK RULE: the prompt must not contain the reference patch or any
   `test_blobs` content. Enforce structurally — `build_prompt` composes only from
   `statement`/`subject`/paths-free fields, and a test asserts no stripped hunk line (len >
   10) of `reference_patch` and no line of any test blob appears in the prompt.
5. Extend tests with a fixture repo whose history contains: a fix commit with `fixes #7` in
   the message that changes source AND a `tests/test_x.py` file; a fix commit touching no
   tests; a non-fix commit. Cover: pair extraction (correct base/fix, reference patch
   non-empty), `oracle_tests_available` true/false split, test-blob content equals the fixed
   file at the fix commit, the leak assertion of step 4, `limit` respected, notes on a
   root-commit skip, and that `mine_issue_tasks` with `use_gh=False` never calls the
   injected `gh_runner` (stub that raises if called).

**Acceptance:** mining is offline by default; task records carry everything grading needs
without ever touching target history again; the leak test exists and fails if the prompt
gains reference content; suite green.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest discover -s tests -p 'test_repo_bench.py' -q
python3 - <<'PY'
import importlib.util, subprocess, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location("repo_bench", "bin/repo_bench.py")
rb = importlib.util.module_from_spec(spec); spec.loader.exec_module(rb)
with tempfile.TemporaryDirectory() as td:
    repo = Path(td) / "r"; repo.mkdir()
    def g(*a): subprocess.run(["git", "-C", str(repo), "-c", "user.name=t",
        "-c", "user.email=t@example.com", *a], check=True, capture_output=True)
    g("init"); (repo / "m.py").write_text("def f():\n    return 1\n")
    g("add", "-A"); g("commit", "-m", "start")
    (repo / "m.py").write_text("def f():\n    return 2\n")
    t = repo / "tests"; t.mkdir(); (t / "test_m.py").write_text("import m\nassert m.f() == 2\n")
    g("add", "-A"); g("commit", "-m", "fixes #7: f returns 2")
    tasks, notes = rb.mine_issue_tasks(repo, gh_runner=None)
    assert len(tasks) == 1, (len(tasks), notes)
    task = tasks[0]
    assert task["mode"] == "issue-replay" and task["issue"] == 7
    assert task["oracle_tests_available"] is True
    assert "tests/test_m.py" in task["test_blobs"]
    prompt = rb.build_prompt(task)
    assert "return 2" not in prompt, "reference/blob content leaked into prompt"
    assert task["statement_source"] == "commit-message"
    assert any("weaker" in l for l in task["labels"])
print("T2 probe OK")
PY
git diff --quiet bin/claude_execute.py bin/cost_report.py bin/routing_scorecard.py bin/bench_routing.py
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T3 — General-mode miner: red-validated mutation-repair tasks
- status: done
- model: sonnet
- depends: T2

**Files:** `bin/repo_bench.py`; `tests/test_repo_bench.py` (extend).

**Why:** mode B (D4) — the fallback when history yields no usable issue→fix pairs: inject a
bug, prove the tests catch it (red), and ask the candidate to find and fix it. Objective
oracle by construction.

**Do:**
1. `MUTATION_OPERATORS` — ordered tuple of `(name, pattern, replacement)` textual operators:
   `==`→`!=`, `<=`→`<`, `>=`→`>`, `+ 1`→`- 1`, `True`→`False`, `true`→`false`,
   ` and `→` or `, `&&`→`||`. One mutation per admitted task; first match wins per
   candidate site.
2. `mine_general_tasks(target_repo, commit, limit=8, test_cmd=None, test_runner=None,
   scratch_dir=None, git_runner=None) -> (tasks, notes)`. Requires `test_cmd` (no test_cmd →
   `ValueError`: general mode needs a test command — D4). Enumerate source files from
   `git_target(..., "ls-tree", "-r", "--name-only", commit)` skipping paths matching
   `DEFAULT_TEST_PATTERNS` and binary-ish suffixes; scan file content (via
   `git_target(..., "show", ...)`) for operator sites; for each candidate mutation (bounded
   scan — stop after examining `limit * 4` sites): build a scratch sandbox via
   `make_sandbox`, apply the single-line mutation, run `test_cmd` through `test_runner`
   (injectable `(cmd, cwd) -> (rc, output)`; default subprocess with `cwd`) — ADMIT the
   task only when rc != 0 (red-validated); green mutations are discarded with a note. Task
   record: same schema as T2 with `"mode": "general"`, `task_id` `"mut-<n>-<file-stem>"`,
   `statement` = "the test suite fails; find and fix the bug" phrasing that NEVER names the
   file or the operator, `reference_patch` = the reverse-mutation diff,
   `oracle_tests_available: True`, label `"synthetic mutation-repair task"`.
3. `choose_mode(issue_tasks, min_needed) -> ("issue-replay"|"general", reason)` — auto mode
   picks issue-replay when `len(issue_tasks) >= min_needed` (T8's `MIN_EVIDENCE_TASKS`,
   already importable as a module constant — define it HERE now, `MIN_EVIDENCE_TASKS = 5`,
   so T4/T8 consume one constant), else general; `reason` is a printable sentence.
4. Extend tests: fixture repo with a mutable source line and a real (tiny, stdlib-only)
   test script wired as `test_cmd` via a STUB `test_runner` (return rc 1 for mutated
   content, rc 0 otherwise — no real subprocess needed); cover: red-validated admission,
   green-mutation discard + note, statement never contains the mutated file's name or the
   operator text, reference patch reverses the mutation (applying it to the mutated file
   yields the original), missing `test_cmd` raises, `choose_mode` both branches.

**Acceptance:** general tasks only exist when a mutation demonstrably breaks the tests; the
statement hides the bug's location; `MIN_EVIDENCE_TASKS = 5` exists once, module-level;
suite green.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest discover -s tests -p 'test_repo_bench.py' -q
python3 - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location("repo_bench", "bin/repo_bench.py")
rb = importlib.util.module_from_spec(spec); spec.loader.exec_module(rb)
assert rb.MIN_EVIDENCE_TASKS == 5
assert any(n == "eq-to-neq" or "==" in p for n, p, r in rb.MUTATION_OPERATORS), rb.MUTATION_OPERATORS
mode, reason = rb.choose_mode([{}] * 2, rb.MIN_EVIDENCE_TASKS)
assert mode == "general" and reason
mode, reason = rb.choose_mode([{}] * 5, rb.MIN_EVIDENCE_TASKS)
assert mode == "issue-replay"
print("T3 probe OK")
PY
git diff --quiet bin/claude_execute.py bin/cost_report.py bin/routing_scorecard.py bin/bench_routing.py
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T3R — Phase 1 remediation: schema parity, miner robustness, and the red candidate sandbox
- status: done
- model: opus
- depends: T3

**Added by execute, not the architect**, in response to the Phase 1 opus review: 11 findings,
all 11 adjudicated real. This task fixes the eight that are Phase-1 code; the other four
(F5, F8, F9, F11b) are recorded in `NOTES.md` as binding constraints on T4–T7.

**Files:** `bin/repo_bench.py`; `tests/test_repo_bench.py` (extend).

**Why:** two of these are contract breaks that would surface only AFTER a live run has spent
money, and one means general mode measures nothing while appearing to work.

**Do:**

1. **F3 (most important) — the general-mode candidate sandbox is GREEN.** `mine_general_tasks`
   mutates only its own throwaway scratch sandbox (deleted when `scratch_dir` is None) and
   stores `reference_patch` = diff(mutated → original). T5 will build the candidate's sandbox
   fresh off `commit`, which is UNMUTATED — so the candidate is told "the test suite fails"
   and handed a passing repo. Fix: add `"setup_patch"` to the general task record — the
   FORWARD mutation diff (original → mutated), git-`apply`-able to a fresh sandbox off
   `commit`. Issue-replay records carry `"setup_patch": None` (their base commit is already
   the buggy state). Document in the module docstring AND as a key comment that any dispatch
   path MUST apply `setup_patch` to the candidate's sandbox before dispatch when it is not
   None. Test: build a fresh sandbox off `commit`, apply `setup_patch`, and assert the
   injected test runner now returns rc != 0 where it returned 0 before.
2. **F1 — general records break the pinned task-record schema.** T2 step 3 pins the record
   keys; T3 said "same schema". The general record omits `issue`, `fix_commit`, `subject`.
   T7's `build_judge_prompt` reads `subject` and `build_prompt` falls back to it, so this is a
   `KeyError` landing after dispatches are already paid for. Fix: general records carry
   `"issue": None`, `"fix_commit": None`, and a generic leak-free `"subject"` that names
   NEITHER the mutated file NOR the operator (the existing statement-leak test must cover
   `subject` too). Test: mine one task in each mode and assert the two records have IDENTICAL
   key sets.
3. **F2 — a fix commit that DELETES a test file aborts the whole issue-mining pass.**
   `git diff --name-only` reports deleted paths, and `git show <sha>:<deleted path>` exits
   128, so `_require_ok` raises and every already-mined pair is lost. Fix: skip that blob with
   a note, using the same skip-and-note idiom the root-commit case already uses. Test: fixture
   history = [good `fixes #2` pair, then a `fixes #3` commit deleting `tests/test_old.py`];
   assert the good pair is still mined and a note names the skipped path.
4. **F4 — one non-UTF-8 file aborts either miner.** `default_git_runner` uses `text=True`
   with strict decoding, so a latin-1 source file raises `UnicodeDecodeError` (a `ValueError`
   subclass, which `main()` swallows into an opaque exit 2). Fix: skip the offending file
   with a note. Do NOT globally set `errors="replace"` in `default_git_runner` — that would
   silently corrupt the test blobs written into grade copies at T6. Test: fixture with a
   latin-1 file that is not a listed binary suffix; both miners complete and note the skip.
5. **F6 — pin the `statement_source` vocabulary.** T3 introduced a third value `"generated"`
   beyond the pinned `"issue"`/`"commit-message"` pair. Add a module constant listing all
   three so T8's renderer is written against the real vocabulary; assert every emitted record's
   `statement_source` is a member.
6. **F7 — stop re-deriving the pricing path.** `_pricing_task_profile_keys` builds
   `PLUGIN_ROOT / "data" / "pricing.json"` and does its own `json.loads` where
   `cost_report.PRICING_PATH` / `cost_report.load_pricing()` already exist (reuse-never-fork,
   and this repo's first invariant is that pricing.json is the single source). Fix: reuse them
   via the existing `_load` accessor. Also apply the same `size_profile` validation to general
   mode that issue mode already does — both emit `size_profile`, only one validates it.
7. **F10 — the demo's fixture builder points `git_sandbox` at something it then calls a
   target.** Rename that helper's git usage (e.g. a `_fixture_git`) so the module-wide reading
   "`git_sandbox` never touches a target" stays airtight. Behavior unchanged.
8. **F11a — `default_test_runner`'s string/`shell=True` path has no test.** The widening is
   accepted (it matches what a user types into `--test-cmd`), but add a test exercising it
   with a harmless stdlib command so the path is covered.

**Do NOT** change what T2 mines (the test blobs are needed by T6's oracle), touch any reused
module, or start any Phase 2 work.

**Acceptance:** both miners emit records with identical key sets; a general task can be made
RED in a fresh sandbox via `setup_patch`; a deleted test path, a non-UTF-8 file, and a green
mutation each degrade with a note instead of aborting; `statement_source` is a pinned
vocabulary; no second pricing.json path literal in the module; suite green and only grows.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest discover -s tests -p 'test_repo_bench.py' -q
python3 - <<'PY'
import importlib.util, subprocess, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location("repo_bench", "bin/repo_bench.py")
rb = importlib.util.module_from_spec(spec); spec.loader.exec_module(rb)

src = Path("bin/repo_bench.py").read_text()
assert 'PLUGIN_ROOT / "data"' not in src, "pricing path still constructed locally (F7)"
assert "PRICING_PATH" in src or "load_pricing" in src, "cost_report pricing loader not reused (F7)"
assert hasattr(rb, "STATEMENT_SOURCES") and len(rb.STATEMENT_SOURCES) == 3, "F6 vocabulary unpinned"

with tempfile.TemporaryDirectory() as td:
    td = Path(td); repo = td / "r"; repo.mkdir()
    def g(*a): subprocess.run(["git", "-C", str(repo), "-c", "user.name=t",
        "-c", "user.email=t@example.com", *a], check=True, capture_output=True)
    g("init")
    (repo / "calc.py").write_text("def classify(n):\n    if n >= 10:\n        return 'big'\n    return 'small'\n")
    g("add", "-A"); g("commit", "-m", "start")
    (repo / "calc.py").write_text("def classify(n):\n    if n >= 10:\n        return 'big'\n    return 'small'\n# fixed\n")
    t = repo / "tests"; t.mkdir(); (t / "test_calc.py").write_text("import calc\n")
    g("add", "-A"); g("commit", "-m", "fixes #4: calc")
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True).stdout.strip()

    issue_tasks, _ = rb.mine_issue_tasks(repo, gh_runner=None)
    assert issue_tasks, "no issue task mined"

    # NOTE (execute): redness must key on the MUTATION itself. An earlier version of this
    # stub keyed on "'big'", which no operator in MUTATION_OPERATORS can remove — so every
    # mutation read as green, zero tasks were admitted, and the clause failed against a
    # correct module. Keep this keyed on the mutated operator text.
    def runner(cmd, cwd):
        return (1, "fail") if "n >= 10" not in (Path(cwd) / "calc.py").read_text() else (0, "ok")
    gen_tasks, _ = rb.mine_general_tasks(repo, head, limit=2,
        test_cmd="true", test_runner=runner, scratch_dir=td / "scratch")
    assert gen_tasks, "no general task mined"

    a, b = set(issue_tasks[0]), set(gen_tasks[0])
    assert a == b, f"schema parity broken (F1): only-issue={a-b} only-general={b-a}"
    assert gen_tasks[0]["setup_patch"], "general task has no setup_patch (F3)"
    assert issue_tasks[0]["setup_patch"] is None, "issue task should carry setup_patch None"
    for task in (issue_tasks[0], gen_tasks[0]):
        assert task["statement_source"] in rb.STATEMENT_SOURCES, task["statement_source"]
    stem = "calc"
    assert stem not in gen_tasks[0]["subject"], "general subject names the mutated file (F1/leak)"
print("T3R probe OK")
PY
git diff --quiet bin/claude_execute.py bin/cost_report.py bin/routing_scorecard.py bin/bench_routing.py
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

## Phase 2 — The priced plan and the money seam

### T4 — `plan`: the priced matrix, and `run`'s structural refusal
- status: done
- model: sonnet
- depends: T3

**Files:** `bin/repo_bench.py`; `tests/test_repo_bench.py` (extend).

**Why:** D1 — the default invocation must do everything EXCEPT spend, and must make the cost
of going live concrete before any dispatch exists.

**Do:**
1. Pricing reuse (D10): lazy-load `cost_report` as `cr` via `_load`; model resolution via
   `ce.resolve_model` (accepts pricing ids or tier words). `estimate_dispatch_usd(model_id,
   profile_key, pricing) -> float`: look up `pricing["task_profiles"][profile_key]` tokens,
   rates via `cr.match_model` + `cr.rates_for` (pass `when=None`-safe current time as
   `rates_for` expects — read its signature, do not guess), arithmetic tokens/1e6 × rate
   only. No literal price anywhere.
2. `build_plan(target_repo, models, mode, limit, test_cmd, judge, pricing, ...) ->
   plan_card`: resolve candidates (dedupe, each must resolve via `ce.resolve_model` — a
   KeyError propagates with its listing message); mine per `mode` (`auto` uses
   `choose_mode`); judge resolution per D6 — default = first model in pricing-file order of
   the HIGHEST populated tier not among the candidates (walk `ce.TIER_ORDER` downward);
   judge ∈ candidates → `ValueError` (D6 hard refusal). Card: repo, base commit
   (`rev-parse HEAD` unless `--commit` given), mode + reason, tasks (id, size_profile,
   oracle availability), candidates, judge, matrix rows (task × candidate: est usd), judge
   grades (one per task × candidate: priced at profile `"XS"`), totals per candidate and
   grand total, labels (estimate caveat: `"planned estimate from task_profiles — not a
   bill"`), notes. `cmd_plan` renders markdown (matrix table + totals + `"to spend: rerun
   with run --live --max-usd <ceiling>"` hint) or `--json`.
3. `cmd_run` gating (structural, D1): without BOTH `--live` and `--max-usd` → print the plan
   exactly as `cmd_plan` would, then a stderr line `refusing to dispatch: run requires
   --live AND --max-usd <ceiling>` and exit 2. Grand total > ceiling → print plan + stderr
   `planned estimate $X exceeds --max-usd $Y — raise the ceiling or shrink the matrix`,
   exit 2, dispatch nothing. (The dispatch path itself lands in T5 — here `cmd_run` with
   both flags and a fitting ceiling writes `plan.json` into a new run dir and exits 0 with
   a `plan recorded; dispatch arrives with the runner` stderr note; T5 replaces that tail.)
4. `plan.json` = the plan card verbatim (`json.dumps(..., indent=2)`), written only under
   the run dir.
5. Extend tests (fixture repo from T2/T3 helpers; fixture pricing dict with fake ids across
   two tiers + `task_profiles`): matrix arithmetic against hand-computed numbers from the
   FIXTURE dict (never real prices); judge default skips candidates; judge==candidate
   raises; `run` refusal paths (missing flags → exit 2 + plan on stdout; ceiling exceeded →
   exit 2, no run dir dispatches); labels present.

**Acceptance:** plan prices every future dispatch (candidates AND judge) from pricing data
at run time; `run` cannot spend without both flags and a sufficient ceiling; suite green.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest discover -s tests -p 'test_repo_bench.py' -q
python3 - <<'PY'
import importlib.util, subprocess, sys, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location("repo_bench", "bin/repo_bench.py")
rb = importlib.util.module_from_spec(spec); spec.loader.exec_module(rb)
with tempfile.TemporaryDirectory() as td:
    repo = Path(td) / "r"; repo.mkdir()
    def g(*a): subprocess.run(["git", "-C", str(repo), "-c", "user.name=t",
        "-c", "user.email=t@example.com", *a], check=True, capture_output=True)
    g("init"); (repo / "m.py").write_text("x = 1\n"); g("add", "-A"); g("commit", "-m", "c1")
    (repo / "m.py").write_text("x = 2\n"); g("add", "-A"); g("commit", "-m", "fixes #1: x")
    r = subprocess.run([sys.executable, "bin/repo_bench.py", "run", "--repo", str(repo),
        "--models", "haiku,sonnet", "--store-dir", str(Path(td) / "store")],
        capture_output=True, text=True)
    assert r.returncode == 2, (r.returncode, r.stderr)
    assert "--live" in r.stderr and "--max-usd" in r.stderr, r.stderr
    p = subprocess.run([sys.executable, "bin/repo_bench.py", "plan", "--repo", str(repo),
        "--models", "haiku,sonnet", "--json"], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    import json; card = json.loads(p.stdout)
    assert card["judge"] and card["judge"] not in card["candidates"], card
    assert any("not a bill" in l for l in card["labels"]), card["labels"]
print("T4 probe OK")
PY
git diff --quiet bin/claude_execute.py bin/cost_report.py bin/routing_scorecard.py bin/bench_routing.py
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T5 — The harness seam and the live dispatch loop (stub-tested; no real spend anywhere)
- status: done
- model: opus
- depends: T4

**Files:** `bin/repo_bench.py`; `tests/test_repo_bench.py` (extend).

**Why:** D1/D2 — the one place real money could ever move. The seam must be injectable
end-to-end, the ceiling enforced before every single dispatch, and the Claude adapter must
reuse `claude_execute`'s argv shape rather than re-deriving it.

**Do:**
1. `OUTPUT_FORMAT_ARGS = ("--output-format", "json")` — ONE constant, MEDIUM confidence,
   commented with the `claude_execute.PERMISSION_FLAG` precedent (R1: a correction is a
   one-line edit against the CLI docs, never a live probe). `CLAUDE_ADAPTER` — dict:
   `{"name": "claude", "build_argv": <wraps ce.build_dispatch(bin_, model_id, prompt,
   extra_args=OUTPUT_FORMAT_ARGS)>, "extract_usage": <fn>}`. `extract_usage(output) ->
   {"input_tokens", "output_tokens", ...}|None` parses the result JSON best-effort (find
   the last JSON object in output; usage keys per the CLI's result shape); ANY parse
   failure → `None`, never a guess. `price_usage(model_id, usage, pricing)` via
   `cr.match_model`/`cr.rates_for` (same reuse rule as T4).
2. `dispatch_cell(task, model_id, adapter, sandbox, runner, claude_bin, ...) -> record`:
   build prompt (T2), argv via adapter, run through `runner(argv, cwd)` (injectable;
   default subprocess with `cwd=sandbox`, capture, text) timing wall-clock via
   `time.monotonic`; capture patch (T1); record `{"task_id", "model", "wall_seconds",
   "usage": ...|None, "usd": <priced|None>, "usd_basis": "actual"|"estimated", "patch",
   "dispatch_rc"}` — when usage is None, `usd` falls back to the plan estimate with
   `usd_basis: "estimated"`.
3. `cmd_run` full loop replacing T4's stub tail: for each task, for each candidate:
   CEILING CHECK FIRST (D1: spent-so-far + this cell's estimate > `--max-usd` → stop the
   whole run cleanly; remaining cells recorded `{"skipped": "cost-ceiling"}`; envelope
   label `"partial (cost-ceiling)"`), build sandbox (fresh per cell), dispatch, write the
   dispatch record under `dispatches/`, delete the sandbox unless `--keep-work`. Judge
   grading is dispatched in T7 — leave a seam (`grade_cells` no-op list here). At the end
   write `results.json` v1: `{store_schema_version, run_id, repo (str), base_commit, mode,
   harness, candidates, judge, cells: [...], spend: {ceiling_usd, spent_usd, basis:
   "actual"|"estimated"|"mixed"}, labels, notes}`. `--claude-bin` flag (default
   `"claude"`) exists so tests can point at a stub executable, mirroring
   `claude_execute`; but unit tests prefer injected runner callables.
4. Safety tests (the point of this task): a full `run --live --max-usd <enough>` over the
   fixture repo with an INJECTED stub runner (writes a file into the sandbox, returns a
   canned result JSON with usage) — assert: every cell dispatched via the stub (count),
   target repo byte-identical after the run (`status --porcelain` empty AND `rev-parse
   HEAD` unchanged), patches captured, `usd_basis: "actual"` when the stub emits usage and
   `"estimated"` when it emits garbage; ceiling test — a tiny `--max-usd` stops before the
   first (or second) dispatch, remaining cells `skipped: cost-ceiling`, envelope label
   present, exit code 0 with the stop stated on stdout (a ceiling stop is a clean outcome,
   not an error); the refusal paths from T4 still hold. Also: the module contains NO
   default-wired path to a real binary in tests — assert `cmd_run` requires `--live`
   (already covered) and that the stub runner saw `OUTPUT_FORMAT_ARGS` in every argv.
5. `demo` grows: stubbed one-candidate run over the self-built fixture (still zero real
   dispatch), printing the matrix, the stop/completion line, and where results.json landed
   (inside the demo's temp dir).

**Acceptance:** every dispatch goes through an injected/injectable runner; ceiling enforced
pre-dispatch per cell; target repo untouched by a full run; results envelope written with
honest spend basis; suite green.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest discover -s tests -p 'test_repo_bench.py' -q
python3 bin/repo_bench.py demo > /tmp/repo_bench_t5_demo.txt
grep -q "results.json" /tmp/repo_bench_t5_demo.txt
python3 - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location("repo_bench", "bin/repo_bench.py")
rb = importlib.util.module_from_spec(spec); spec.loader.exec_module(rb)
assert rb.OUTPUT_FORMAT_ARGS == ("--output-format", "json")
assert rb.CLAUDE_ADAPTER["name"] == "claude"
assert rb.extract_usage("no json here at all") is None
src = open("bin/repo_bench.py").read()
assert "PERMISSION_FLAG" not in src.replace("ce.PERMISSION_FLAG", "").replace(
    "claude_execute.PERMISSION_FLAG", ""), "argv shape re-derived instead of reused"
print("T5 probe OK")
PY
git diff --quiet bin/claude_execute.py bin/cost_report.py bin/routing_scorecard.py bin/bench_routing.py
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T5R — Phase 2 remediation: close the filesystem leak, fix general mode on real repos
- status: done
- model: opus
- depends: T5

**Added by execute, not the architect**, after the Phase 2 review: 11 findings, all 11
adjudicated real. This task fixes eight. P2-F5 (T7), P1-F5 (T6) and P2-F11 (T11) are recorded
in `NOTES.md` as constraints on later tasks; F10 is fixed by running T10.

**Files:** `bin/repo_bench.py`; `tests/test_repo_bench.py` (extend).

**Why:** finding 1 invalidates the whole measurement premise — the candidate can read the
reference fix off the filesystem. Finding 2 means general mode crashes on any repo whose
tests produce artifacts (i.e. every Python repo).

**Do:**

1. **F1 (HIGHEST) — the solution is reachable from the candidate's cwd.** Candidates run with
   `cwd=<run-dir>/work/cell-NNN` and permissions bypassed. Reachable today by `cat`:
   `../<task_id>.setup.patch` (reverse it → the general-mode answer); `../site-N/.git` (mining
   scratch sandboxes, never swept, whose init commit is the unmutated source);
   `../../tasks/<task_id>.json` (**`reference_patch` AND `test_blobs`, both modes**, written
   BEFORE the loop); `../../dispatches/*.json` (earlier candidates' captured patches —
   cross-candidate contamination). PLAN D3's "unreachable by construction" is true of git
   history and false of the filesystem, and `test_mined_task_records_land_in_the_store_never_in_the_sandbox`
   passes unchanged with the reference one `../` away.
   **The rule to establish: while ANY dispatch is live, the candidate's ancestor directories
   contain no solution material.** Note this pulls against F11b (sandboxes under the run dir
   for D3/D11 honesty) — keep sandboxes under the run dir and make the run dir clean instead
   of moving sandboxes out. Concretely:
   - Buffer `tasks/*.json` and `dispatches/*.json` in memory during the loop and write them
     after it (grading is their only consumer). Combine with item 5's `try/finally` so a
     crash still writes them.
   - Hold each `setup_patch` in a temp file OUTSIDE the run dir; unlink it immediately after
     `git apply`.
   - `rmtree` each `site-N` mining sandbox as soon as its red check is done (this is also F8).
   - Sweep each cell sandbox immediately after its patch is captured, so a later candidate
     cannot read an earlier one's work. Under `--keep-work`, print an explicit warning that
     kept sandboxes disable inter-cell leak isolation and the flag must not be used for
     measurement runs.
   - **Test the real property, not the old proxy:** walk EVERY ancestor directory of each cell
     sandbox up to the run dir (and the run dir itself) during a live-stubbed dispatch, and
     assert no file there contains reference-patch or test-blob content. The existing
     cell-dir-only assertion is the defect; keep it and add this.
2. **F2 (HIGH) — general mode crashes on any repo whose tests produce artifacts.**
   `mine_general_tasks` runs the target's real `--test-cmd` in the site sandbox and then does
   `git add -A`, sweeping in `__pycache__` and friends. `setup_patch` therefore carries binary
   hunks and `prepare_cell_sandbox`'s `git apply` fails (`cannot apply binary patch ...
   without full index line`), raising out of the loop into exit 2 — reproduced with
   `--test-cmd "python3 t.py"`. The suite is blind because every general-mode test injects a
   stub runner that executes nothing. Fix: derive both `setup_patch` and `reference_patch`
   from the MUTATED FILE PATH ONLY (the mutation is a known single-line change to one known
   file), so test artifacts cannot enter either patch. Also fixes the secondary effect where
   artifacts inflated `_changed_loc` → `size_profile` → the priced estimate.
   **Test with a test command that really does produce artifacts** (e.g. a real `python3`
   invocation that imports a module, creating `__pycache__`) — a stub runner cannot catch this
   class, which is exactly why it survived.
3. **F3 — actual spend can exceed the ceiling and nothing says so.** A probe recorded
   `spent_usd: 75.0` against `ceiling_usd: 5.0` and rendered identically to a clean preventive
   stop. The overshoot itself is unavoidable (a dispatch's cost is unknown until it returns)
   and the projection rule matches D1 — the missing part is NAMING it. Two fixes: the
   `STOPPED:` branch must carry the spend basis (the `completed:` branch already does — that
   asymmetry is the exact drift signal GUARDRAILS names), and the envelope must carry an
   explicit overspend label whenever `spent_usd > ceiling_usd`.
4. **F4 — the adapter is missing D2's fourth member.** PLAN D2 pins the contract as `name`,
   `build_argv`, `extract_usage`, **`pricing loader`**; `CLAUDE_ADAPTER` has three, and
   `dispatch_cell`/`cmd_run` hardwire `_cr().load_pricing()` instead. A codex/copilot adapter
   would therefore be priced from `data/pricing.json` unless those functions are edited —
   which is not "drops in". Add the pricing-loader member and route pricing through the
   adapter. Do NOT build a codex or copilot adapter (out of scope); the stub adapter in tests
   proves the seam.
5. **F6 — an exception in the dispatch loop loses the envelope.** Only `build_plan` is wrapped
   in try/except; anything raising inside the loop skips the `results.json` write, so the run
   has no envelope, no basis, no labels — the one artifact D8 says must always carry the
   honesty labels. Wrap the loop in `try/finally` that always writes `results.json`, with an
   `aborted` note and label when it did not complete.
6. **F7 — `price_usage` re-implements `cost_report.price` term for term.** D10 is the kit's
   sharpest fence and says the only local arithmetic is tokens × rate. The mitigation is real
   (harness usage keys don't match `price()`'s, and returning `None` where `price()` would
   `KeyError` is the honest degradation) — so fix it as a KEY-MAPPING WRAPPER around `cr.price`
   that preserves the `None`-on-missing-key behavior, not by adopting `price()` wholesale.
7. **F9 — a false safety claim, and the suite really does shell out.**
   `default_test_runner`'s docstring says it "is never exercised by a test here"; it is —
   `test_refused_run_still_mines_under_the_run_dir_before_cleanup` drives `main()` with no
   injected `test_runner`, so `subprocess.run("run-tests", shell=True, ...)` executes a
   PATH-resolved command during `unittest discover`. Fix the docstring to be true AND inject a
   runner in that test so nothing PATH-resolved runs. That test also redirects only stderr and
   dumps a whole plan card into the suite's stdout — silence it.

**Do NOT** weaken any leak assertion, widen `READ_ONLY_GIT`, build a codex/copilot adapter,
touch a reused module, or start Phase 3 work.

**Acceptance:** no solution material exists anywhere in a cell sandbox's ancestry while a
dispatch is live, proven by an ancestor-walking test; general mode completes with an
artifact-producing test command; a ceiling overshoot is labeled and carries its basis; the
adapter carries a pricing loader; a mid-loop exception still writes a labeled envelope;
`price_usage` wraps `cr.price`; no test shells out to a PATH-resolved command; suite green and
only grows.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest discover -s tests -p 'test_repo_bench.py' -q
python3 bin/repo_bench.py demo > /tmp/repo_bench_t5r_demo.txt
grep -q "results.json" /tmp/repo_bench_t5r_demo.txt
python3 - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location("repo_bench", "bin/repo_bench.py")
rb = importlib.util.module_from_spec(spec); spec.loader.exec_module(rb)
assert "pricing" in " ".join(rb.CLAUDE_ADAPTER.keys()).lower(), \
    f"adapter still missing a pricing loader member (F4): {sorted(rb.CLAUDE_ADAPTER)}"
src = open("bin/repo_bench.py").read()
assert "cr.price" in src or "_cr().price" in src, "price_usage does not wrap cost_report.price (F7)"
assert "finally" in src, "no try/finally guarding the envelope write (F6)"
print("T5R probe OK")
PY
git diff --quiet bin/claude_execute.py bin/cost_report.py bin/routing_scorecard.py bin/bench_routing.py
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T5R2 — close the last two solution leaks: sandbox history, and plan.json
- status: done
- model: opus
- depends: T5R

**Added by execute.** T5R's implementer found and reported these two while fixing F1; they
were outside its stated scope, so it correctly left them. The orchestrator reproduced both.

**Files:** `bin/repo_bench.py`; `tests/test_repo_bench.py` (extend).

**Why:** F1 established the rule "while any dispatch is live, the candidate cannot reach
solution material." T5R enforced it for ANCESTOR directories. These two are the remaining
holes — one inside the candidate's own sandbox, one in a file T5R did not defer.

**Do:**

1. **The cell sandbox's own git history leaks the general-mode answer.**
   `prepare_cell_sandbox` applies `setup_patch` and commits it ON TOP of the init commit, so
   the sandbox has two commits and the injected bug is readable from inside the candidate's
   own working directory. Reproduced:
   ```
   task_id: mut-1-calc
   sandbox commits: 2
   bug readable via 'git log -p' INSIDE the sandbox: True
   ```
   `git diff HEAD~1 HEAD` reversed IS the fix, so general-mode measurement is still worthless.
   Fix: leave exactly ONE commit in the sandbox — `git commit --amend` (or equivalent) so the
   injected bug is part of the single root commit with no history to mine.
   Two invariants that must survive, both already tested elsewhere — do not break them:
   - `sandbox_init_commit`'s single-root assumption (`rev-list --max-parents=0 HEAD`);
   - `capture_patch`'s baseline. After the amend, the root commit contains the injected bug,
     so a captured patch must still show ONLY the candidate's own work and never the bug
     injection. Assert this explicitly.
   Test: after `prepare_cell_sandbox` on a general-mode task, `rev-list --count HEAD` is 1,
   `git log -p` inside the sandbox contains no mutation content, and a simulated candidate
   edit captures cleanly.

2. **`plan.json` sits in the candidate's ancestry and names the mutated file.** It is written
   into the run dir before the loop, and general-mode task ids are `mut-N-<stem>` — so
   `cat ../../plan.json` narrows the search to one file even with T5R's other fixes in place.
   Fix: give it the same treatment T5R gave `tasks/*.json` and `dispatches/*.json` — buffer
   and write it after the dispatch loop, inside the same `try/finally`.
   **Do not break T4's non-dispatch path:** when `cmd_run` is invoked with valid flags but
   never dispatches (the plan-recorded path), `plan.json` must still be written immediately as
   it is today — there is no candidate to leak to. Defer only when dispatches will run.

3. **Extend `SolutionAncestryTests`** so it would catch both of these: assert the sandbox's own
   git history is clean of mutation content, and that no file in the ancestry (including
   `plan.json`) reveals the mutated file's name during a live general-mode dispatch.

**Do NOT** move sandboxes out of the run dir (F11b/D3/D11), weaken any existing leak
assertion, or start Phase 3 work.

**Acceptance:** a general-mode candidate cannot recover the injected bug from its own sandbox
history, from any ancestor directory, or from a task id in `plan.json`, during a live
dispatch; `capture_patch` still reports only candidate work; suite green and only grows.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest discover -s tests -p 'test_repo_bench.py' -q
python3 - <<'PY'
import importlib.util, subprocess, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location("repo_bench", "bin/repo_bench.py")
rb = importlib.util.module_from_spec(spec); spec.loader.exec_module(rb)
with tempfile.TemporaryDirectory() as td:
    td = Path(td); repo = td / "r"; repo.mkdir()
    def g(*a): subprocess.run(["git","-C",str(repo),"-c","user.name=t",
        "-c","user.email=t@example.com",*a], check=True, capture_output=True)
    g("init")
    (repo/"calc.py").write_text("def classify(n):\n    if n >= 10:\n        return 'big'\n    return 'small'\n")
    g("add","-A"); g("commit","-m","c1")
    head = subprocess.run(["git","-C",str(repo),"rev-parse","HEAD"],
        capture_output=True,text=True,check=True).stdout.strip()
    def runner(cmd, cwd): return (1,"fail") if "n >= 10" not in (Path(cwd)/"calc.py").read_text() else (0,"ok")
    tasks, notes = rb.mine_general_tasks(repo, head, limit=1, test_cmd="x",
        test_runner=runner, scratch_dir=td/"scratch")
    assert tasks, notes
    cell = td / "cell"
    rb.prepare_cell_sandbox(tasks[0], repo, cell)
    n = subprocess.run(["git","-C",str(cell),"rev-list","--count","HEAD"],
        capture_output=True,text=True,check=True).stdout.strip()
    assert n == "1", f"sandbox history still mineable: {n} commits"
    # THE REAL PROPERTY (corrected by execute): the ORIGINAL, pre-mutation line must be
    # unrecoverable from any git channel. The MUTATED line is legitimately present -- it is
    # the buggy base state the candidate is handed and asked to fix. An earlier version of
    # this clause asserted the mutated line was absent from `log -p`, which no correct
    # implementation can satisfy: `log.showRoot` defaults true, so the root commit renders as
    # a whole-tree creation diff that necessarily contains the candidate's own base state.
    orig = b"if n >= 10:"
    def sh_t(*a): return subprocess.run(["git","-C",str(cell),*a],capture_output=True,
                                        text=True,errors="replace").stdout
    def sh_b(*a): return subprocess.run(["git","-C",str(cell),*a],capture_output=True).stdout
    assert orig not in sh_t("log","-p").encode("utf-8","replace"), "original readable in log"
    assert orig not in sh_t("reflog").encode("utf-8","replace"), "original readable in reflog"
    assert orig not in sh_b("cat-file","--batch-all-objects","--batch"), \
        "original recoverable from a dangling object"
    assert not sh_t("fsck","--lost-found").strip(), "dangling objects survive in the sandbox"
    assert "n > 10" in (cell / "calc.py").read_text(), "the bug is missing from the worktree"
    (cell / "candidate_work.py").write_text("# candidate edit\n")
    patch = rb.capture_patch(cell)
    assert "candidate_work.py" in patch, "capture_patch lost the candidate's work"
    assert "classify" not in patch, "capture_patch is reporting the injected bug as candidate work"
print("T5R2 probe OK")
PY
git diff --quiet bin/claude_execute.py bin/cost_report.py bin/routing_scorecard.py bin/bench_routing.py
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

## Phase 3 — Grading oracles

### T6 — Oracles (a) tests and (b) structural similarity
- status: done
- model: sonnet
- depends: T5

**Files:** `bin/repo_bench.py`; `tests/test_repo_bench.py` (extend).

**Why:** D5 — the objective backbone (`solved` is oracle-(a)-only, forever) and the
always-available similarity signal, each with its own honest degradation.

**Do:**
1. `oracle_tests(task, sandbox_path, test_cmd, test_runner, scratch_dir) -> dict`. Grades in
   a COPY (`shutil.copytree`) of the post-dispatch sandbox — NEVER the sandbox the candidate
   worked in, and never before dispatch: write `task["test_blobs"]` into the copy
   (issue-replay; general mode has no blobs — the repo's own tests are already there), run
   `test_cmd` via `test_runner` with cwd=copy. Result `{"oracle": "tests", "available":
   bool, "passed": bool|None, "rc", "notes"}`. Unavailable when: no test_cmd, or
   issue-replay with `oracle_tests_available` False — `passed` stays None with a note,
   never False (absence is not failure — D5).
2. Red-check at base (issue-replay only, once per task per run, cached): copy of a CLEAN
   base sandbox + blobs + run; if it PASSES at base, the oracle for that task is labeled
   `"tests already pass at base — not a discriminating oracle"`, `available` False for
   verdict purposes (R6). (General-mode tasks were red-validated at mining.)
3. `oracle_structural(reference_patch, candidate_patch) -> dict`: parse both diffs
   (paths + hunk line sets, stdlib string work — no external diff lib): `{"oracle":
   "structural", "files_jaccard": float, "hunk_overlap": float, "loc_delta_ratio": float,
   "out_of_scope_files": int, "label": "similarity signal — NOT a correctness verdict"}`.
   Empty candidate patch → all-zero metrics + note `"candidate produced no change"`. The
   label string is REQUIRED on every result (test asserts it).
4. Wire both into `cmd_run`'s per-cell flow after patch capture (tests oracle only when
   test_cmd given), results into each cell record under `"oracles"`.
5. Tests: issue-replay fixture — a stub runner that makes the sandbox pass/fail the blob
   test both ways; blobs never appear in the CANDIDATE sandbox (assert file absent there,
   present in the grade copy); red-check demotion path (fixture where base already passes);
   general-mode grading without blobs; structural metrics on hand-built patches (identical
   → jaccard 1.0; disjoint → 0.0; empty candidate); the mandatory similarity label.

**Acceptance:** `solved` can only ever come from a red-then-green test run in a grade copy;
blobs never touch the candidate's sandbox; structural results always carry the
similarity-not-correctness label; suite green.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest discover -s tests -p 'test_repo_bench.py' -q
python3 - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location("repo_bench", "bin/repo_bench.py")
rb = importlib.util.module_from_spec(spec); spec.loader.exec_module(rb)
r = rb.oracle_structural("", "")
assert r["label"] == "similarity signal — NOT a correctness verdict", r
ref = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a = 1\n+a = 2\n"
same = rb.oracle_structural(ref, ref)
assert same["files_jaccard"] == 1.0, same
other = rb.oracle_structural(ref, "--- a/y.py\n+++ b/y.py\n@@ -1 +1 @@\n-b\n+c\n")
assert other["files_jaccard"] == 0.0, other
print("T6 probe OK")
PY
git diff --quiet bin/claude_execute.py bin/cost_report.py bin/routing_scorecard.py bin/bench_routing.py
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T7 — Oracle (c): the blind LLM judge
- status: done
- model: sonnet
- depends: T6

**Files:** `bin/repo_bench.py`; `tests/test_repo_bench.py` (extend).

**Why:** D6 — the subjective leg, priced and bias-controlled: blind slots, judge never a
candidate, structural parse or honest failure.

**Do:**
1. `build_judge_prompt(task, reference_patch, candidate_patch, slot_seed) -> (prompt,
   slots)`: the issue statement plus two patches labeled `Patch A` / `Patch B`; which slot
   holds the candidate is randomized from `slot_seed` (injectable int; CLI uses
   `secrets.randbelow(2)` per grade) and returned as `slots = {"A": "reference"|"candidate",
   "B": ...}` for the audit record. The prompt asks for a STRICT one-line verdict grammar:
   `GRADE A=<correct|partial|incorrect> B=<...> EQUIVALENT=<yes|no>` plus free-text
   rationale after it. Nothing in the prompt names which patch is which.
2. `parse_judge_output(output, slots) -> dict|None`: find the grammar line; map slots back
   to candidate/reference; return `{"candidate_grade", "reference_grade", "equivalent",
   "slots"}`; anything unparseable → None.
3. `oracle_judge(task, reference_patch, candidate_patch, judge_model, adapter, runner,
   claude_bin, pricing, slot_seed=None) -> dict`: dispatch via the SAME runner seam
   (ceiling-checked by the caller like any dispatch — wire the judge grades into
   `cmd_run`'s loop after each cell, each grade its own priced dispatch); result
   `{"oracle": "judge", "judge_model", "grade": <parsed>|None, "usd", "usd_basis",
   "label": "subjective LLM-judge grade vs reference — bias-controlled, not ground
   truth"}`; parse failure → `grade: None` + note `"judge output unparseable"` (never a
   default grade).
4. Enforcement already promised in T4 stays: judge ∈ candidates is a flag-time refusal;
   ADD the belt-and-braces runtime assert in `oracle_judge` itself (`ValueError`).
5. Tests: slot randomization honors the seed both ways and slots map back correctly (feed
   a stub runner canned `GRADE ...` lines; assert candidate_grade follows the slot, not
   the letter); unparseable output → None grade + note; judge==candidate raises; prompt
   contains both patches and never the words "reference" / "candidate" in the patch
   labels; judge dispatches count against the ceiling (extend the T5 ceiling test: a
   ceiling that covers cells but not grades stops before grading with
   `skipped: cost-ceiling` on the grade records).

**Acceptance:** blind slots audited per grade; no unparseable output ever becomes a score;
judge spend rides the same ceiling; suite green.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest discover -s tests -p 'test_repo_bench.py' -q
python3 - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location("repo_bench", "bin/repo_bench.py")
rb = importlib.util.module_from_spec(spec); spec.loader.exec_module(rb)
task = {"statement": "fix the bug", "task_id": "t1", "subject": "s"}
p0, s0 = rb.build_judge_prompt(task, "REFPATCH", "CANDPATCH", 0)
p1, s1 = rb.build_judge_prompt(task, "REFPATCH", "CANDPATCH", 1)
assert s0 != s1 and {"A", "B"} == set(s0) == set(s1)
g = rb.parse_judge_output("noise\nGRADE A=correct B=partial EQUIVALENT=no\nmore", s0)
assert g and g["slots"] == s0 and g["candidate_grade"] in ("correct", "partial")
assert rb.parse_judge_output("no grammar here", s0) is None
print("T7 probe OK")
PY
git diff --quiet bin/claude_execute.py bin/cost_report.py bin/routing_scorecard.py bin/bench_routing.py
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T7R — Phase 3 remediation: blind the judge, make `solved` unforgeable, save the envelope
- status: done
- model: opus
- depends: T7

**Added by execute** after the Phase 3 review: 6 findings, all 6 adjudicated real. F1/F2/F3
are blockers — each defeats a core claim the tool makes about its own numbers.

**Files:** `bin/repo_bench.py`; `tests/test_repo_bench.py` (extend).

**Do:**

1. **F1 (CRITICAL) — the judge can read the answer key from its own ancestry.** `oracle_judge`
   builds its cwd under `scratch_dir`, and `cmd_run` passes `work_dir` — so the judge runs at
   `<run-dir>/work/repo-bench-judge-XXXX` while `tasks/<id>.json` (containing
   `reference_patch` AND `test_blobs`) and `dispatches/<id>__<model>.json` (containing the
   candidate's MODEL ID) sit two levels up, written before grading in the same block.
   Measured: from the judge's cwd, `../../tasks` and `../../dispatches` are both populated and
   `../../plan.json` is present. The judge argv carries the permission bypass and its prompt
   has no stay-put instruction. This collapses blind `Patch A`/`Patch B` into a labelled pair
   and additionally reveals which model produced the candidate — the precise fact D6 exists to
   hide.
   Fix BOTH ways (defense in depth): (a) build the judge's cwd OUTSIDE the run dir entirely —
   the judge never touches the target and is not a candidate sandbox, so D3/D11's
   under-the-run-dir rule does not apply to it; (b) defer the `tasks/`, `dispatches/` and
   `plan.json` writes until AFTER grading completes, the same buffering T5R already
   established.
   **Delete the test exclusion that waved this through** and replace it: the ancestry hunt
   must cover EVERY dispatch cwd — candidate and judge alike — asserting neither can reach
   reference-patch content, test blobs, or any candidate model id. The judge legitimately
   receives both patches IN ITS PROMPT; it must not be able to learn which is which, or whose,
   from the filesystem.
2. **F2 (HIGH) — `solved` is forgeable.** `oracle_tests` copies the POST-dispatch sandbox and
   restores only `task["test_blobs"]` — the paths the FIX COMMIT touched. General mode has no
   blobs at all, so nothing is restored: a candidate that never fixes the bug and instead
   rewrites the test to trivially pass grades `{"available": true, "passed": true}` with the
   bug still in the tree. Reproduced. Issue-replay is only partly protected — gutting a test
   file the fix did not touch (a runner, a `conftest`, a config) also passes.
   Fix: in the grade copy, restore the ENTIRE test surface from the BASE tree before running —
   every path matching the test patterns at `base_commit`, via the existing read-only
   `git_target` seam — then apply the fix's `test_blobs` on top (issue-replay). The candidate's
   changes to any test file must not survive into grading, in either mode.
   ADDITIONALLY: when a candidate's captured patch touches a test-pattern path, record that on
   the cell as an explicit flag/note. It is not proof of gaming, but T8 must be able to see it,
   and a `solved` earned alongside test edits deserves to be visible.
3. **F3 (HIGH) — a raising judge dispatch destroys the results envelope.** `grade_cells` runs
   inside `cmd_run`'s `finally` BEFORE `results.json` is written, so any exception it raises
   (a vanished binary, a pricing failure, a temp-dir failure) aborts the `finally` before the
   write — real candidate dollars spent, and the one artifact D8 says must ALWAYS carry spend,
   basis and labels does not exist. Reproduced. This is exactly the Phase 2 F6 defect the
   `finally` was created to fix; T7 reintroduced it by adding a spending step above the write.
   Fix: grading gets its own guarded block that cannot abort the envelope write; a grading
   failure is recorded as a note/label on the envelope, and the envelope write is
   unconditional and last.
4. **F4 (MEDIUM-HIGH) — `_strip_test_hunks` can empty the reference, silently.** Three
   reproduced triggers: a tests-only fix commit (`fix flaky test / Fixes #3` — and such a task
   still counts toward the D7 evidence floor); a binary-only source change (`Binary files ...
   differ` has no `+++` line, so no block parses); and `color.ui = always` in the TARGET's git
   config — the reference diff is taken with no flags and inherits it, while the candidate diff
   correctly pins `--no-color --no-ext-diff`, so ANSI escapes make every line unparseable and
   `size_profile` collapses to XS for every task in that repo.
   Downstream, an empty reference means the judge's `Patch A` renders EMPTY (100%
   deanonymization, and the meaningless grade parses fine and is recorded as real), and
   structural returns `0.0` for a correct candidate while counting its one real file as out of
   scope.
   Fix: (a) pin `--no-color --no-ext-diff` on the reference diff; (b) give `oracle_structural`
   an `available` channel — when the stripped reference is empty it is UNAVAILABLE with a note,
   rendering `n/a`, never `0.0`; (c) when a task's stripped reference is empty, do not dispatch
   a judge grade for it — record it unavailable with a note instead of paying for a
   deanonymized, meaningless grade.
5. **F5 (MEDIUM) — a ceiling stop that only cut judge grades prints "0 skipped".** The
   `dispatched`/`skipped` counters on the STOPPED line count CELLS only, so a stop that cut
   every grade tells the user it skipped nothing. The envelope is honest; the terminal line is
   not. Fix: the stop line must account for skipped GRADES too.
6. **F6 (MEDIUM) — general mode carries an unlabelled residual judge tell.** The reference is
   by construction the exact inverse of one `MUTATION_OPERATORS` entry — one file, ±1 line —
   while the candidate's patch is real agent output. Nothing to fix structurally; the defect is
   that `JUDGE_LABEL` claims "bias-controlled" without qualification. Fix: in general mode the
   judge result must carry an explicit note that blinding is materially weaker because the
   reference is a synthetic one-line inverse.

**Also fix the nits** (cheap, and each is a small honesty leak): `oracle_structural("garbage",
"garbage")` returns `loc_delta_ratio: 1.0` — perfect agreement from zero parsed data; a
whitespace-only candidate patch misses the "candidate produced no change" note because the
short-circuit is `if not candidate_patch`; and `oracle_tests` runs BEFORE the red check, so the
target's arbitrary test command executes once per cell even for tasks the red check then
demotes — run the red check first.

**Also add** the T7-informational item from NOTES.md: assert directly that an aborted run's
envelope carries `grades: []`.

**Do NOT** weaken any leak assertion, widen `READ_ONLY_GIT`, change what T2/T3 mine, touch a
reused module, or start Phase 4 work.

**Acceptance:** no dispatch of any kind — candidate or judge — can reach reference content,
test blobs, or a candidate model id from its filesystem ancestry; a candidate that edits tests
instead of fixing the bug CANNOT be `solved` in either mode, and test-touching candidates are
flagged; a raising judge dispatch still produces a labelled envelope; an empty stripped
reference renders `n/a` and buys no judge grade; the reference diff is color-proof; a
grades-only ceiling stop says so; general-mode judge results carry the weaker-blinding note;
suite green and only grows.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest discover -s tests -p 'test_repo_bench.py' -q
python3 bin/repo_bench.py demo > /tmp/repo_bench_t7r_demo.txt
grep -q "results.json" /tmp/repo_bench_t7r_demo.txt
python3 - <<'PY'
import importlib.util, inspect
spec = importlib.util.spec_from_file_location("repo_bench", "bin/repo_bench.py")
rb = importlib.util.module_from_spec(spec); spec.loader.exec_module(rb)
# F4a: the reference diff must be color-proof like the candidate diff
src = inspect.getsource(rb.mine_issue_tasks)
assert "--no-color" in src, "reference diff not pinned --no-color (F4)"
# F4b: structural must have an unavailability channel
r = rb.oracle_structural("", "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n")
assert "available" in r, f"oracle_structural has no available channel (F4): {sorted(r)}"
assert r["available"] is False, f"empty reference must render unavailable, got {r}"
assert r.get("files_jaccard") is None, f"unavailable structural must not render a number: {r}"
# nit: garbage in must not yield perfect agreement
g = rb.oracle_structural("garbage", "garbage")
assert g.get("loc_delta_ratio") in (None, 0.0), f"garbage yielded {g.get('loc_delta_ratio')}"
print("T7R probe OK")
PY
git diff --quiet bin/claude_execute.py bin/cost_report.py bin/routing_scorecard.py bin/bench_routing.py
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

## Post-completion — gaps found by real use (execute-authored, after kit sign-off)

### T21 — `regrade`: finish a run's judge grades after a ceiling stop
- status: done
- model: opus
- depends: T20

**Added by execute.** The first completed live run (`2026-08-10-d89a`) hit its $25 ceiling
mid-grading: all 14 cells dispatched, but 6 of 14 judge grades were skipped
`cost-ceiling` and there is NO way to finish them — a ceiling stop during grading
permanently strands the judge column. Ceiling stops are a designed, permanent behavior
(D1), so resume-grading is a missing structural capability, not a one-run patch.

**Files:** `bin/repo_bench.py`; `tests/test_repo_bench.py`; `skills/repo-bench/SKILL.md`.

**Do:**
1. New subcommand `regrade --run <id> [--store-dir] --live --max-usd <ceiling>
   [--judge-seed ...]`. The spend gate is IDENTICAL to `run`'s (D1): refuse exit 2 without
   BOTH flags, `validate_ceiling` before anything, `would_exceed_ceiling` before EVERY
   grade dispatch. A fresh ceiling for this invocation — never a continuation of the old
   run's ceiling arithmetic.
2. It re-dispatches ONLY grade records whose skip reason was `cost-ceiling`. Grades that
   completed stay byte-identical; `empty-reference` skips stay skipped (they are not budget
   casualties and re-dispatching them buys a deanonymized grade — T7R law). Candidate cells
   are NEVER re-dispatched — the candidates' work is done; this touches the judge leg only.
3. All the judge disciplines hold unchanged: blind slots re-randomized per grade with the
   audit record kept, judge==candidate refusal, unparseable → `None` + note, judge cwd
   outside the run dir, prompts built from the stored task records (reference stripped of
   test hunks exactly as `grade_cells` does — reuse it, do not re-derive).
4. **Envelope honesty across invocations.** `results.json` is rewritten (still the one
   writer) with: the new grades merged in; a `regrades` entry recording this invocation's
   run id, ceiling, spend and basis; combined spend reported WITHOUT blurring bases
   (per-invocation lines, not one mixed number); the `partial (cost-ceiling)` label
   removed ONLY when no cost-ceiling skips remain anywhere, else retained; a note naming
   what this regrade finished. A regrade that itself hits its ceiling stops cleanly,
   labels honestly, and remains resumable.
5. `verdict` re-rendered after a regrade must pick up the new grades with zero code
   changes (it reads the envelope). Assert that with a test, not a claim.
6. Tests (stub runners only, no real CLI): refusal without flags; nan/inf/negative ceiling
   refused before any dispatch; only cost-ceiling skips re-dispatched (completed grades
   byte-identical, empty-reference untouched, candidate cells untouched — assert all
   three); mid-regrade ceiling stop honest and resumable; envelope merge idempotent-safe
   (a second regrade with nothing to do changes nothing and says so); verdict picks up
   merged grades; the leak fences: nothing a regrade writes lands anywhere
   candidate-reachable (trivially true — no candidates are live — but assert the store
   buffering shape is preserved).
7. `skills/repo-bench/SKILL.md`: document `regrade` beside `run`, same plan-first framing
   (it spends; it needs its own explicit ceiling; a stranded judge column is the signal to
   use it).

**Do NOT** re-dispatch candidate cells, touch `solved` or anything routing-grade, weaken
any label, or let a regrade delete or reorder existing cells/grades.

**Acceptance:** a ceiling-stranded judge column can be finished under a fresh explicit
ceiling with every judge discipline intact; envelopes stay honest across invocations;
completed work is provably untouched; suite green and only grows.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest discover -s tests -p 'test_repo_bench.py' -q
python3 bin/repo_bench.py regrade --help 2>&1 | grep -q -- '--max-usd'
python3 - <<'PY'
import importlib.util, subprocess, sys, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location("repo_bench", "bin/repo_bench.py")
rb = importlib.util.module_from_spec(spec); spec.loader.exec_module(rb)
r = subprocess.run([sys.executable, "bin/repo_bench.py", "regrade", "--run", "x"],
                   capture_output=True, text=True)
assert r.returncode == 2 and "--live" in r.stderr and "--max-usd" in r.stderr, \
    f"regrade spend gate missing: rc={r.returncode} {r.stderr[:120]}"
print("T21 probe OK")
PY
python3 bin/repo_bench.py demo > /tmp/rb_t21_demo.txt
grep -q "BELOW EVIDENCE FLOOR" /tmp/rb_t21_demo.txt
grep -nE '"npm"|"pip"|pip install|npm ci' tests/test_repo_bench.py && exit 1 || echo "no test invokes a real installer"
git diff --quiet bin/claude_execute.py bin/cost_report.py bin/routing_scorecard.py bin/bench_routing.py
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T20 — the full-patch diagnostic: bound the false negatives without reopening the forgery
- status: done
- model: opus
- depends: T19

**Added by execute after the first completed live run** (`benchruns/2026-08-10-d89a`, pyright,
7 tasks × haiku+sonnet, $25.18). The run worked, but 9 of 14 cells carried the
`not solved WITH work reverted from outside the reference patch's scope` flag — haiku 5/7,
sonnet 4/7. The whitelist reverts any candidate change outside the reference patch's files, so
a CORRECT fix placed in a different file (sonnet's issue-11475 had work reverted from
`analyzer/typeEvaluatorTypes.ts`, a plausible fix site) reads `not solved`. The absolute rates
systematically understate every candidate, and nothing in the output bounds HOW MUCH.

**What must NOT change — state it before the fix:** the scope rule IS the forgery protection.
The harness forgery (`run_tests.py` → `sys.exit(0)`) was closed precisely because out-of-scope
changes never reach the substrate, and T12R/T17R's lesson is that enumeration cannot make
widening safe. Therefore `solved` remains in-scope-tests-only, forever (R6). Any number that
includes out-of-scope work is forgeable BY CONSTRUCTION and may never feed `solved`, the
capability order, the D7 floor, the tier map, the daily-driver pick, or `apply`.

**The fix — a second, labeled, diagnostic grade:**

1. **`oracle_tests_full_patch(...)`** — grades a substrate built as: pristine base +
   `setup_patch` (general mode) + the candidate's ENTIRE captured patch + the reference test
   blobs, with the test surface still restored from base first (T7R law — test-file edits
   still cannot count), artifacts still hash-verified, in its own fresh copy that is swept
   after. Result shape mirrors `oracle_tests` plus a mandatory label:
   `"full-patch DIAGNOSTIC — includes out-of-scope changes the candidate made, including
   files the test command may execute; forgeable by construction; NEVER routing-grade"`.
2. **Run it conditionally** — only when ALL of: the tests oracle is available; the in-scope
   grade was `passed: False`; and `candidate_modified_out_of_scope` is non-empty. That is
   exactly the false-negative-suspect population (9 of 14 cells in the live run). A cell whose
   in-scope grade passed, or that had no out-of-scope work, records the diagnostic as
   not-run (`None` + reason), spending nothing. `--no-full-patch-check` disables it entirely
   for users who want the old cost profile; absent flag = on, because the diagnostic is the
   honest default.
3. **The ceiling covers it.** Each diagnostic run executes `--test-cmd` once more (~90s on
   pyright, $0 in model spend — it is toolchain time). Record its wall-clock in its own field
   (never in the cell's `wall_seconds`, same rule as setup time). No model dispatch is
   involved, so `would_exceed_ceiling` is not in play — but say so in the code comment rather
   than leaving the absence ambiguous.
4. **Render it as a bound, not a score.** In the verdict's measurement table, a new diagnostic
   column showing `-` (not run), `still fails`, or `PASSES — possible false negative`. In the
   per-candidate section, one line:
   `false-negative bound: N of the M not-solved cells pass with the full patch applied —
   solved lies in [solved_n, solved_n + N] of objective_n; the upper bound is DIAGNOSTIC
   (forgeable), the lower bound is routing-grade`. The capability order, tier map, floor, and
   daily-driver pick use ONLY the lower bound, unchanged. The existing false-negative NOTE on
   flagged cells now cites the diagnostic result instead of speculating.
5. **The forgery stays visible in the diagnostic.** When a diagnostic passes AND the
   candidate's out-of-scope paths are listed, the reader can see `run_tests.py` there if it
   was touched. Do not attempt to classify paths as "harness-adjacent" — that is the
   enumeration mistake again. List the applied out-of-scope paths on the diagnostic result,
   verbatim, and let the label carry the trust level.
6. **Ask both leak questions of the new substrate** (NOTES: construction AND lifetime). It
   contains candidate-written bytes BY DESIGN — that is its purpose — so the questions
   invert: (a) it must never contaminate the in-scope substrate, the template artifact
   store, or any later cell's grading — build it in its own copy, after the in-scope grade
   completes, and sweep it before the next dispatch; (b) nothing from it may be written
   anywhere a later candidate could read (the store buffering rules apply to its records
   exactly as to dispatch records).
7. **Tests** (stub runners, fixture repos, no real installers):
   - the pyright pattern: candidate fixes the bug in a DIFFERENT source file → in-scope
     `not solved` + diagnostic PASSES + the bound line renders with the right arithmetic;
   - the forgery pattern: candidate rewrites the `--test-cmd` entry point, touching no
     test-pattern path → in-scope `not solved` + diagnostic passes + `run_tests.py` listed
     verbatim in the applied paths + `solved`/floor/tier/daily-driver all UNCHANGED —
     assert each of those four explicitly;
   - genuine failure: both grades fail → bound adds nothing;
   - the conditional gate: diagnostic not run when in-scope passed, when no out-of-scope
     work existed, or when `--no-full-patch-check` is set;
   - isolation: after a diagnostic run, the in-scope substrate result is byte-identical to
     a run with the diagnostic disabled (property test), and no diagnostic artifact survives
     into the next cell's ancestry (extend the ancestry sweep);
   - a mutation check on the rendering: a diagnostic pass must be UNABLE to increment
     `solved_n` — assert by constructing the verdict from a results.json where the
     diagnostic passed and confirming `solved_n` ignores it.
8. **`skills/repo-bench/SKILL.md`**: document the diagnostic, the bound-not-score rule, the
   `--no-full-patch-check` flag, and the reading order: the interval `[lower, upper]` is the
   honest answer; quoting the upper bound alone is quoting a forgeable number.

**Do NOT** let the diagnostic feed `solved` or anything downstream of it, classify out-of-scope
paths by name, run the diagnostic before the in-scope grade, leave its substrate or records
readable by a later candidate, or weaken any existing leak/forgery assertion.

**Acceptance:** the false-negative population gets a measured bound; `solved` and everything
downstream is provably unchanged by diagnostic results; the forgery case is visible and
harmless; the conditional gate and isolation properties hold; suite green and only grows.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest discover -s tests -p 'test_repo_bench.py' -q
python3 - <<'PY'
import importlib.util, inspect
spec = importlib.util.spec_from_file_location("repo_bench", "bin/repo_bench.py")
rb = importlib.util.module_from_spec(spec); spec.loader.exec_module(rb)
assert callable(getattr(rb, "oracle_tests_full_patch", None)), "diagnostic oracle missing"
src = open("bin/repo_bench.py").read()
assert "NEVER routing-grade" in src, "diagnostic label missing its trust level"
osrc = inspect.getsource(rb.oracle_tests_full_patch)
assert "label" in osrc, "diagnostic result carries no label"
print("T20 probe OK")
PY
python3 bin/repo_bench.py demo > /tmp/rb_t20_demo.txt
grep -q "BELOW EVIDENCE FLOOR" /tmp/rb_t20_demo.txt
grep -qiE 'full-patch|false negative' /tmp/rb_t20_demo.txt
grep -nE '"npm"|"pip"|pip install|npm ci' tests/test_repo_bench.py && exit 1 || echo "no test invokes a real installer"
git diff --quiet bin/claude_execute.py bin/cost_report.py bin/routing_scorecard.py bin/bench_routing.py
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T19 — close the two recorded gaps: failure-path deletion, and the exclusion count
- status: done
- model: sonnet
- depends: T18

**Added by execute** to close the two gaps recorded in NOTES as known-but-unfixed. Neither is
a defect in shipped behavior; both are places where correct behavior is unproven or a reported
number is misleading.

**Files:** `bin/repo_bench.py`; `tests/test_repo_bench.py`.

**Do:**

1. **The setup-FAILURE path has no test.** T17R's verifier confirmed BY HAND that
   `work/templates/<key>/build` is deleted even when the setup command fails (it observed
   setup rc=7 leaving neither the build dir nor the key dir behind), and recorded that this
   specific path has no dedicated test. Hand-verification is not coverage: the deletion sits
   outside the `if record["ok"]:` block today, and nothing would catch a future edit that moved
   it inside. Add a test that a FAILING `--setup-cmd` (non-zero rc, stub runner) leaves no
   build tree and no key dir under the run dir — and, since a failed template is still recorded
   and never retried, assert the failure record itself survives with its exit code so the
   `available: False` / `SETUP_FAILED` path keeps its evidence.

2. **F8 — the exclusion count scans past `--limit`.** In `mine_issue_tasks` the
   `--exclude-subject` check precedes the `len(tasks) >= limit` break, so once the limit is met
   the walk keeps going over excluded commits until it meets the next non-excluded pair. With
   `--limit 1` against a history of bumps this reported `3 commit(s) excluded` for a run that
   needed to examine one. T17R's implementer declined to reorder it because the count's meaning
   and T13's tests both depend on the current order — and that reasoning is sound.
   **So do not reorder. Make the number honest instead:** the exclusions reported must be those
   encountered while mining the tasks actually planned. Either stop counting once the limit is
   met, or keep the count and say plainly in the label that the walk continued past the limit.
   Pick one, state the rationale in a comment, and cover it with a test using `--limit 1`
   against a fixture whose history holds several excluded commits. Do NOT weaken any existing
   T13 assertion — if one encodes the old count as law, report that rather than editing it.

**Do NOT** change what is mined, alter any leak fence, touch a reused module, or reorder the
exclusion check.

**Acceptance:** a failing setup command is proven by test to leave no build tree while keeping
its failure record; the exclusion count either matches the tasks actually planned or says why
it does not; suite green and only grows.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest discover -s tests -p 'test_repo_bench.py' -q
python3 bin/repo_bench.py demo > /tmp/rb_t19_demo.txt
grep -q "BELOW EVIDENCE FLOOR" /tmp/rb_t19_demo.txt
grep -nE '"npm"|"pip"|pip install|npm ci' tests/test_repo_bench.py && exit 1 || echo "no test invokes a real installer"
git diff --quiet bin/claude_execute.py bin/cost_report.py bin/routing_scorecard.py bin/bench_routing.py
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```


### T18 — `plan` must say how wrong its own estimates have been
- status: done
- model: sonnet
- depends: T17R

**Added by execute after the first LIVE run** (`benchruns/2026-08-05-515a`, $5.70 actual).
Measured on `issue-11570` (size=S), all three candidates:

    model    actual     estimated   ratio
    haiku    $0.5203    $0.06       8.7x
    sonnet   $1.2760    $0.12       10.6x
    opus     $3.5838    $0.30       11.9x

The 10-task matrix was planned at $17.22; at these rates it is **$100-200**. `task_profiles`
models token counts for a generic task, not a real agentic session on a large TypeScript
codebase. The ceiling caught this exactly as designed — but the ceiling is currently the ONLY
thing between a user and a 10x surprise, and a user reading `grand total: $17.22` will size
their ceiling against a number that is off by an order of magnitude.

**Files:** `bin/repo_bench.py`; `tests/test_repo_bench.py`; `skills/repo-bench/SKILL.md`.

**Do:**
1. **Report, do not silently adjust.** The plan card gains a calibration line derived from the
   run store's own recorded actuals — e.g. `calibration: past runs cost 9.8x their estimate
   (median over 3 cell(s) in 1 run(s), size S, models haiku/sonnet/opus)`. Do NOT multiply the
   estimates by a fudge factor: a silently-corrected number is exactly the kind of confident
   fiction this kit has spent 23 tasks refusing to print. The estimate stays what
   `task_profiles` says; the calibration line stands beside it.
2. **Derive it honestly from the store.** Read completed cells across prior runs
   (`results.json` → cells with `usd_basis: "actual"` and a recorded estimate). Report the
   MEDIAN ratio with its sample size, and break it down by `size_profile` and by model where
   there is enough data to do so — a ratio from one size-S cell must not be presented as
   applying to size L. Where a run recorded no actuals, it contributes nothing rather than a
   guess.
3. **Say so when there is no history.** With an empty or absent store, print a plain line
   saying no calibration data exists yet and that `task_profiles` estimates are unvalidated —
   never omit the line silently, because its absence would read as "the estimate is fine".
4. **Optional explicit application.** If you add a way to apply the calibration to the printed
   total, it must be an explicit flag (e.g. `--calibrated`), must label the result as
   calibrated-from-N-cells rather than as an estimate, and must never be the default.
5. Tests: fixture run dirs in a TEMP store with known actual/estimate pairs — assert the median
   ratio, the sample count, the per-size breakdown, the empty-store line, and that the
   uncalibrated total is unchanged. Never read the real `benchruns/`.
6. Update `skills/repo-bench/SKILL.md`: state that `task_profiles` estimates have measured
   ~10x low on a large real codebase, that the calibration line is the honest signal, and that
   a ceiling should be sized against calibration rather than the raw estimate.

**Do NOT** silently scale estimates, present a calibrated figure as an estimate, invent a ratio
from zero data, or read the real store in tests.

**Acceptance:** the plan card carries a calibration line derived from recorded actuals or says
plainly that none exist; the raw estimate is unchanged; the ratio reports its sample size and
does not over-generalize across sizes; suite green and only grows.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest discover -s tests -p 'test_repo_bench.py' -q
python3 - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location("repo_bench", "bin/repo_bench.py")
rb = importlib.util.module_from_spec(spec); spec.loader.exec_module(rb)
src = open("bin/repo_bench.py").read()
assert "calibration" in src.lower(), "no calibration reporting"
print("T18 probe OK")
PY
grep -qi 'calibrat' skills/repo-bench/SKILL.md
git diff --quiet bin/claude_execute.py bin/cost_report.py bin/routing_scorecard.py bin/bench_routing.py
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T17R — the setup-artifact store is a candidate-writable answer key (BLOCKING)
- status: done
- model: opus
- depends: T17

**Added by execute** after the post-completion review of T13–T17 — the review T17 never got
before shipping. 9 findings, all 9 adjudicated real. T13–T16 are sound. T17 is not.

**F1 (CRITICAL) — a candidate forges its own `solved` by writing into the shared artifact
store.** `GradeTemplates` keeps setup output at `<run-dir>/work/templates/<key>/artifacts` for
the whole run, and `overlay` re-reads that directory from disk on EVERY grading. The
candidate's cwd is `work/cell-NNN`, so the store is one `../` away and WRITABLE. Reproduced
end-to-end with stub runners:

    dispatch cell-002 poisoned: ['templates/<key>/artifacts/vendor/dep.py']
    mut-1-calc x claude-sonnet-5: available=True passed=True out_of_scope=[] touched_tests=[]

That cell made NO change in its own sandbox. It overwrote the shared artifact, `overlay`
copied those bytes into its substrate, and the suite went green. `node_modules/<pkg>/index.js`
is the same shape on a real target. This breaks the whitelist invariant literally — the
substrate contains bytes the candidate wrote — defeats the D7 floor (forged cells count as
objective evidence and are `apply`-eligible), and leaves NO trace in the candidate's patch, so
both evidence fields are empty. All three T17 mechanisms survive intact; artifacts were never
in the threat model.

**F2 (HIGH) — `--setup-key` overlays one task's artifacts onto another task's substrate.**
Two tasks with different `base_commit`s but identical keyed content share one record, and its
artifacts came from whichever was graded first. Reproduced:

    substrate A: app.py="VERSION = 'A'"  dist/app.py="VERSION = 'A'"
    substrate B: app.py="VERSION = 'B'"  dist/app.py="VERSION = 'A'"

On a compiled target — the `npm ci && npm run build` case the skill recommends this flag for —
task B's grade measures task A's source and the candidate's in-scope patch is irrelevant.
`_setup_artifact_paths` also captures REWRITTEN TRACKED FILES individually, so this is not
limited to new build dirs. The unstated premise is "setup output is a function of the setup
command alone" — false for any compile.

**F3 (HIGH) — retained artifacts are a cross-task answer key in the READ direction.** A
candidate on task 2 can read `../templates/<keyOfTask1>/artifacts/dist/beta.py` — the pristine
version of the exact file it was asked to repair. Keying on `setup_patch` stops tasks SHARING a
template; it does not stop them COEXISTING.

**F4 (MEDIUM) — the load-bearing safety claim is false**, at `bin/repo_bench.py:1972`,
`bin/repo_bench.py:2975`, and `skills/repo-bench/SKILL.md:213`: "A template is built before any
candidate for that task has been dispatched." Templates are prepared LAZILY INSIDE GRADING,
which runs after `dispatch_cell` — cell-001 sees no template, cell-002 onward do. This sentence
is why F1/F3 looked impossible to every reader including the orchestrator.

**F5 (MEDIUM) — the guarding tests cannot reach the hazard.** The property test's task comes
from `_oracle_task`, which pins `setup_patch: None` even for `mode="general"`, so it never
exercises the setup-patch mechanism at all. The adversarial sweep plants into the CANDIDATE'S
OWN SANDBOX — the previous ring — never into the artifact store, and no test runs more than one
task with a template in play.

**Files:** `bin/repo_bench.py`; `tests/test_repo_bench.py`; `skills/repo-bench/SKILL.md`.

**Do:**

1. **F1 + F3 — the artifact store must be unreachable from a candidate.** The precedent is
   T7R, which moved the judge's dispatch cwd OUT of the run dir for exactly this reason and
   documented it as a deliberate D11 carve-out. Do the same here: the setup COMMAND may still
   execute under `work/` (that is the mutation D11 governs), but the captured artifact store is
   inert data and must live outside the candidate-reachable tree entirely — note that anything
   under the run dir is reachable via `../..`, so "move it up a level" is not a fix.
   **Additionally, as defense in depth: hash every artifact at capture and verify before each
   overlay**, refusing with a note on mismatch. Two independent mechanisms, because this is the
   sixth ring of this leak family and each previous single fix was one ring short.
2. **F2 — stop sharing artifacts that cannot be shared.** `--setup-key` is sound only when
   setup output depends on the keyed paths alone — true for a pure dependency install, false
   for any build step. At minimum: refuse to carry across tasks any artifact path that is
   TRACKED at either task's base commit (a rewritten tracked file is never a shareable
   install artifact), and state in the skill that `--setup-key` must not be used when
   `--setup-cmd` compiles. If you can detect the unsound case structurally rather than by
   documentation, prefer that and say what you did.
3. **F4 — make the claim true or delete it.** Replace the temporal claim in all three places
   with what actually holds: no candidate tree, patch, or path is an input to template
   preparation. That statement is true, provable, and does not imply the false safety the
   current wording does.
4. **F5 — make the tests reach the hazard.** The property test must exercise a real
   general-mode task with a non-None `setup_patch`. The adversarial sweep must plant INTO THE
   ARTIFACT STORE, not only into the candidate's sandbox. Add a multi-task test with templates
   in play, since F1/F2/F3 all require more than one task to manifest.
5. **F6 — the enrichment label renders on general-mode cards.** `build_plan` computes it from
   `issue_tasks` and appends it before general mode replaces `tasks`, so a general-mode card
   reports a ratio about tasks that are not in the run — and spends a real `gh` call per
   discarded issue task. Compute it only when the resolved mode is issue-replay.
6. **F7 — an absent `--setup-key` path silently collapses every task to one template.**
   `key_basis` records `absent`, so a typo (`--setup-key package.lock`) keys every task
   identically — the maximum-amplitude case of F2. Refuse, or warn loudly with a label.
7. **F8 (nit) — the exclusion count scans past `--limit`.** It errs toward visibility, so fix
   only if free. **F9 — `demo` has no `--setup-cmd` coverage**; the Done-means smoke never
   exercises the new grading input. Add it.

**Do NOT** weaken any existing leak assertion, leave the artifact store anywhere under the run
dir, keep a safety claim that is not true, or ship `--setup-key` sharing for build output.

**Acceptance:** a candidate cannot read OR write the artifact store; artifacts are hash-verified
before overlay; no artifact crosses tasks whose bases differ where that could change the
substrate; the safety claim states only what holds; the property test and adversarial sweep both
reach the artifact store with a real general-mode task; the enrichment label appears only on
issue-replay cards; suite green and only grows.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest discover -s tests -p 'test_repo_bench.py' -q
python3 - <<'PY'
import importlib.util, inspect
spec = importlib.util.spec_from_file_location("repo_bench", "bin/repo_bench.py")
rb = importlib.util.module_from_spec(spec); spec.loader.exec_module(rb)
src = open("bin/repo_bench.py").read()
assert "built before any candidate" not in src, "the false temporal safety claim survives (F4)"
skill = open("skills/repo-bench/SKILL.md").read()
assert "built before any candidate" not in skill, "the false claim survives in the skill (F4)"
print("T17R probe OK")
PY
python3 bin/repo_bench.py demo > /tmp/rb_t17r_demo.txt
grep -q "BELOW EVIDENCE FLOOR" /tmp/rb_t17r_demo.txt
grep -nE '"npm"|"pip"|pip install|npm ci' tests/test_repo_bench.py && exit 1 || echo "no test invokes a real installer"
git diff --quiet bin/claude_execute.py bin/cost_report.py bin/routing_scorecard.py bin/bench_routing.py
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T17 — `--setup-cmd`: make targets with a build/install step benchmarkable
- status: done
- model: opus
- depends: T16

**Added by execute at the user's direction**, after pyright's plan proved the task supply is
good (6–8 usable tasks, clears the D7 floor) but the grading loop is impractical: sandboxes are
`git archive` tree extractions with no `node_modules`, so every grading would need `npm ci`
before jest — ~30 installs plus ~10 min of jest each, 5+ hours for one matrix. This is the
blocker for every target with a build or install step, not just pyright.

**Files:** `bin/repo_bench.py`; `tests/test_repo_bench.py`; `skills/repo-bench/SKILL.md`.

**Do:**

1. **`--setup-cmd CMD`** — an optional command run inside a sandbox BEFORE `--test-cmd`, through
   the SAME injectable runner seam `--test-cmd` already uses. Absent = today's behavior exactly.
   Never invented by the tool; never run against the plugin repo. It carries the same D11
   exposure as `--test-cmd` (it executes arbitrary code from/for the target), so it is opt-in
   and documented in the same breath.

2. **Prepared template, or this feature is pointless.** Running setup per grading is ~30
   installs — worse than the problem. Instead build a PREPARED TEMPLATE: a sandbox made from
   the pristine base tree, with `--setup-cmd` run in it ONCE, which grade substrates then COPY
   instead of re-extracting.
   **This is safe only because the template is built from base before any candidate exists, and
   that property is load-bearing — state it in the code and prove it in a test.** A template
   must never be built from, or contaminated by, a candidate's tree, or it becomes a new
   channel into the grade substrate and re-opens the class of defect T7R/T12R closed. The
   whitelist invariant stands unchanged and must be restated in terms of the template:

       grade substrate = (pristine base + setup artifacts) + candidate's IN-SCOPE patch
                         + reference test blobs — and nothing else.

   Extend the existing substrate property test to assert byte-identity against that triple with
   a template in play, and extend the adversarial plant sweep to confirm no plant reaches a
   templated substrate either.

3. **Template cache key.** Each task's base is its own fix commit's parent, so keying on base
   commit alone yields one install per task (10, not 30 — a real win but not the best one). Add
   optional repeatable `--setup-key PATH`: when given, the template is keyed on the content
   hash of those paths at the base commit (e.g. `--setup-key package-lock.json`), so tasks whose
   dependencies are identical share ONE template. Default (no `--setup-key`) keys on the base
   commit. Report how many templates were prepared and how many gradings reused each — a cache
   that silently misses is indistinguishable from no cache.

4. **Setup failure makes the oracle UNAVAILABLE, never failed.** If `--setup-cmd` exits
   non-zero, every grading depending on that template records the tests oracle as
   `available: False` with a note naming the setup failure and its exit code — `passed` stays
   `None`. Absence is not failure (D5); a broken toolchain must never read as "the model didn't
   solve it". This is the single most important honesty rule in the task.

5. **Setup time is not model latency.** Oracle (d) measures dispatch wall-clock; template
   preparation must be recorded separately (e.g. a per-run `setup_seconds` with the template
   count) and must never be folded into a cell's `wall_seconds`, or the daily-driver pick gets
   poisoned by build time that no model is responsible for.

6. **Templates live under the run dir** and are swept with the rest of `work/` unless
   `--keep-work` (which already warns it disables inter-cell isolation). Never a system temp
   dir — D3/D11.

7. Tests: stub runners only; assert setup runs once per template rather than per grading;
   assert `--setup-key` collapses templates when the keyed content matches and does not when it
   differs; assert a failing setup yields `available: False` + note and never `passed: False`;
   assert setup time is absent from `wall_seconds`; assert absent `--setup-cmd` is
   byte-identical to today. **No test may invoke a real `npm`, `pip`, or any network install** —
   stub the runner, exactly as `--test-cmd` is stubbed.

8. Update `skills/repo-bench/SKILL.md`: document `--setup-cmd` and `--setup-key`, state the D11
   exposure plainly (it runs arbitrary commands — only benchmark repos whose build you would
   run by hand), and explain when it is needed (any target that must install or compile before
   its tests run).

**Do NOT** run setup inside a candidate's sandbox, build a template from anything but the
pristine base, let a setup failure render as a failed cell, fold setup time into dispatch
latency, invent a default setup command, or invoke a real installer from any test.

**Acceptance:** a target needing an install step can be graded; setup runs once per template,
not per grading; `--setup-key` collapses identical-dependency tasks to one template; a failing
setup renders `n/a` with a note and never a failure; setup time never enters `wall_seconds`;
the whitelist invariant holds with templates in play, proven by the extended property test and
adversarial sweep; absent `--setup-cmd` is byte-identical to today; suite green and only grows.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest discover -s tests -p 'test_repo_bench.py' -q
python3 bin/repo_bench.py plan --help 2>&1 | grep -q -- '--setup-cmd'
python3 bin/repo_bench.py run  --help 2>&1 | grep -q -- '--setup-key'
python3 - <<'PY'
import importlib.util, inspect
spec = importlib.util.spec_from_file_location("repo_bench", "bin/repo_bench.py")
rb = importlib.util.module_from_spec(spec); spec.loader.exec_module(rb)
src = open("bin/repo_bench.py").read()
assert "setup_cmd" in src, "no setup command support"
# the tests oracle must be able to render UNAVAILABLE on a setup failure
osrc = inspect.getsource(rb.oracle_tests)
assert "available" in osrc
print("T17 probe OK")
PY
grep -nE '"npm"|"pip"|pip install|npm ci' tests/test_repo_bench.py && exit 1 || echo "no test invokes a real installer"
python3 bin/repo_bench.py demo > /tmp/rb_t17_demo.txt && grep -q "BELOW EVIDENCE FLOOR" /tmp/rb_t17_demo.txt
git diff --quiet bin/claude_execute.py bin/cost_report.py bin/routing_scorecard.py bin/bench_routing.py
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T16 — `gh issue view` silently returns PR bodies, mislabelled as issue text
- status: done
- model: sonnet
- depends: T15

**Added by execute after real use.** Measured against microsoft/pyright with
`--with-gh --gh-repo microsoft/pyright`: enrichment reported `10/10 task(s) used real issue
text`, and leakage went UP from 6/10 to 7/10.

**The defect:** GitHub shares ONE number namespace between issues and pull requests, and
`gh issue view <N>` resolves a PR number happily, returning the PR body. Since `(#N)` in a
squash-merge subject IS a PR number, most enrichment fetches a PR description — the leakiest
text available, because a PR description explains the CURE. A sample of what landed in
`statement_source: issue`:

    Fix bool narrowing for numeric literal patterns
    ## Summary
    - Preserve `Literal[False]` and `Literal[True]` when matching the numeric literal patterns
    - Remove those bool literals from the fallthrough branch because ...

Symbols newly leaked through this path include
`getTypeNarrowingCallbackForAssignmentExpression`, `dataClassDuplicateKwOnly`,
`reportDeprecated`. **The mislabelling is the worst part**: those tasks are stamped
`statement_source: issue`, telling a reader the statement is trustworthy exactly when it is
least trustworthy. The tool became more confident and less correct.

The premise is sound — genuine issue references DO work. `Fix #11450:` fetched a real
260-character bug report and scored clean; 3 of 10 tasks came out clean that way. The
implementation simply cannot tell an issue from a PR.

**Files:** `bin/repo_bench.py`; `tests/test_repo_bench.py`; `skills/repo-bench/SKILL.md`.

**Do:**
1. Discriminate before trusting. `gh api repos/<OWNER>/<NAME>/issues/<N>` returns a
   `pull_request` key when the number is a PR and omits it for a real issue. Use that (or an
   equally reliable discriminator you verify) instead of `gh issue view`, which cannot tell
   them apart.
2. **A PR body must never become the statement.** When the number resolves to a PR, fall back
   to the commit-message statement with the existing
   `statement from commit message (weaker than issue text)` label, plus a note reading
   `#N is a pull request, not an issue — PR descriptions explain the fix, so its body was not
   used`. Do NOT use the PR title either; it is usually the same as the commit subject the
   fallback already supplies.
3. `statement_source` must be `issue` ONLY when a real issue body was used. That field is how
   a reader weighs the verdict; it must never overstate.
4. The enrichment label must count only genuine issues and say what happened to the rest —
   e.g. `gh enrichment: 3/10 task(s) used real issue text (7 were pull requests)`. A ratio
   that counts PR bodies as successes is the defect this task exists to remove.
5. Keep every T14/T15 guarantee: `--with-gh` requires `--gh-repo`; unset is byte-identical to
   today; `gh_runner` is never a parameter default; **no test, verify command, or demo may
   invoke a real `gh`** — stubs only, including for the new `gh api` shape.
6. Update `skills/repo-bench/SKILL.md`: state that `(#N)` squash subjects are PR numbers, that
   PR bodies are deliberately refused because they describe the fix, and that the enrichment
   ratio is the number to read before trusting a verdict on such a repo.

**Do NOT** use a PR body or title as a statement, count PRs as enrichment successes, widen
`READ_ONLY_GIT`, or invoke a real `gh` from any test.

**Acceptance:** a PR number never contributes its body; `statement_source: issue` implies a
genuine issue; the enrichment label distinguishes issues from PRs; suite green and only grows.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest discover -s tests -p 'test_repo_bench.py' -q
python3 - <<'PY'
import importlib.util, inspect
spec = importlib.util.spec_from_file_location("repo_bench", "bin/repo_bench.py")
rb = importlib.util.module_from_spec(spec); spec.loader.exec_module(rb)
src = inspect.getsource(rb.mine_issue_tasks)
assert "pull_request" in src, "no PR discriminator in the enrichment path"
for fn in (rb.mine_issue_tasks, rb.build_plan):
    assert inspect.signature(fn).parameters["gh_runner"].default is None
print("T16 probe OK")
PY
grep -nE 'subprocess[^\n]*"gh"|default_gh_runner' tests/test_repo_bench.py && exit 1 || echo "no test reaches a real gh"
git diff --quiet bin/claude_execute.py bin/cost_report.py bin/routing_scorecard.py bin/bench_routing.py
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T15 — `--gh-repo`: the gh lookup resolves the WRONG repository
- status: done
- model: sonnet
- depends: T14

**Added by execute after real use.** Found by the first live `--with-gh` run: enrichment
reported `0/10 task(s) used real issue text`, and the cause was not the expected PR-number
case.

**Files:** `bin/repo_bench.py`; `tests/test_repo_bench.py`; `skills/repo-bench/SKILL.md`.

**The defect:** the gh argv is
`["gh", "issue", "view", str(issue), "--json", "title,body"]` — with **no `--repo`**. `gh`
therefore resolves the repository from the CURRENT WORKING DIRECTORY, not from the target
repo being benchmarked. Reproduced:

    $ gh issue view 11450 --json title,body            # cwd = polytropos
    GraphQL: Could not resolve to an issue or pull request with the number of 11450

    $ gh issue view 11450 --repo microsoft/pyright --json title
    {"title":"[FR]: `struct.unpack` type inference"}

So EVERY lookup fails whenever cwd is not the target — which is the normal case, since the
tool is run from the plugin repo against a target elsewhere. The argv dates from T2; T14 wired
it without noticing. No test could catch this: GUARDRAILS correctly forbids any test from
invoking a real `gh`, so the defect is only reachable through real use.

**Do:**
1. Add `--gh-repo OWNER/NAME` to the shared mining args; thread it to `mine_issue_tasks` as
   `gh_repo=None`, and pass `--repo <OWNER/NAME>` in the gh argv when set.
2. **`--with-gh` without `--gh-repo` must REFUSE** (exit 2, plain sentence naming the missing
   flag) rather than silently querying whatever repo the cwd happens to resolve to. A silent
   wrong-repo lookup is exactly what produced a confident, meaningless `0/10`. Refusing loudly
   beats degrading quietly here, because the degradation LOOKS like a real measurement.
3. **Do NOT infer the repo from the target's `origin` remote.** `remote`/`config` are not in
   `READ_ONLY_GIT` and GUARDRAILS forbids widening that allowlist. Explicit is also more
   correct: benchmarking a FORK would infer the fork, while its issues live upstream.
4. Validate the `--gh-repo` value shape (`owner/name`, no scheme, no trailing path) and refuse
   with a plain sentence otherwise — never pass an unvalidated string into an argv.
5. Tests (stubs only — no test may invoke a real `gh`): the argv carries
   `--repo OWNER/NAME` when `gh_repo` is set; `--with-gh` without `--gh-repo` exits 2 and
   dispatches nothing; a malformed `--gh-repo` refuses; `--gh-repo` without `--with-gh` is
   accepted and simply unused (no lookup); and with both set plus a stubbed success, the
   statement source becomes `issue` and the enrichment label counts it.
6. Update `skills/repo-bench/SKILL.md`: document `--gh-repo`, state that `--with-gh` requires
   it, and explain WHY (gh resolves from cwd; a fork's issues live upstream).

**Do NOT** widen `READ_ONLY_GIT`, infer the repo from a remote, invoke a real `gh` from any
test/verify/demo, or touch a reused module.

**Acceptance:** `--with-gh --gh-repo owner/name` reaches the right repository; `--with-gh`
alone refuses; a malformed value refuses; no test invokes a real `gh`; suite green and only
grows.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest discover -s tests -p 'test_repo_bench.py' -q
python3 bin/repo_bench.py plan --help 2>&1 | grep -q -- '--gh-repo'
python3 - <<'PY'
import subprocess, sys, tempfile
from pathlib import Path
with tempfile.TemporaryDirectory() as td:
    repo = Path(td) / "r"; repo.mkdir()
    def g(*a): subprocess.run(["git","-C",str(repo),"-c","user.name=t",
        "-c","user.email=t@example.com",*a], check=True, capture_output=True)
    g("init"); (repo/"m.py").write_text("x=1\n"); g("add","-A"); g("commit","-m","start")
    (repo/"m.py").write_text("x=2\n"); g("add","-A"); g("commit","-m","fixes #7: real fix")
    r = subprocess.run([sys.executable,"bin/repo_bench.py","plan","--repo",str(repo),
        "--models","haiku","--with-gh"], capture_output=True, text=True)
    assert r.returncode == 2, f"--with-gh without --gh-repo was ACCEPTED (rc={r.returncode})"
    assert "gh-repo" in r.stderr, r.stderr
    bad = subprocess.run([sys.executable,"bin/repo_bench.py","plan","--repo",str(repo),
        "--models","haiku","--with-gh","--gh-repo","https://github.com/o/n"],
        capture_output=True, text=True)
    assert bad.returncode == 2, "a malformed --gh-repo was accepted"
print("T15 probe OK")
PY
grep -q -- '--gh-repo' skills/repo-bench/SKILL.md
grep -nE 'subprocess[^\n]*"gh"|default_gh_runner' tests/test_repo_bench.py && exit 1 || echo "no test reaches a real gh"
git diff --quiet bin/claude_execute.py bin/cost_report.py bin/routing_scorecard.py bin/bench_routing.py
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T14 — `--with-gh`: wire the issue-text seam PLAN D4 specified but no task ever built
- status: done
- model: sonnet
- depends: T13

**Added by execute after kit sign-off.** PLAN D4 says issue enrichment is "OPTIONAL, behind a
flag, through an injectable runner, and never invoked by any test." The runner seam, the
`use_gh` parameter and the `gh issue view` code path all exist and are stub-tested — **but no
task ever created the flag**, so the path is unreachable from the CLI. That is an architect
gap, not a defect in any prior task.

**Files:** `bin/repo_bench.py`; `tests/test_repo_bench.py`; `skills/repo-bench/SKILL.md`.

**Why it matters now:** measured on microsoft/pyright, ~4 of 10 mined statements LEAK THE FIX,
because the repo squash-merges PR descriptions into commit messages and a PR description
describes the cure, not the bug (one names `_getCallableVariableOverrideComparison`, a private
helper the fix introduces). The issue body describes the bug. This flag is the only mitigation
the design has.

**Do:**
1. Add `--with-gh` (store_true) to the SHARED mining args so `plan` and `run` both accept it.
   When set, `cmd_plan`/`cmd_run` pass `use_gh=True` AND a real subprocess `gh` runner into
   `build_plan`. When unset: `use_gh=False` and `gh_runner=None`, **byte-identical to today**.
2. `default_gh_runner(argv) -> (rc, output)` — a module-level subprocess runner, constructed
   ONLY on the `--with-gh` path. It must never be the default value of any parameter: the
   library keeps `gh_runner=None`, exactly as now, so no import or unset invocation can reach
   a real `gh`.
3. **Honest degradation at every failure point**, each with its own note, never a silent
   fallback and never a fabricated statement: `gh` not on PATH; `gh` present but not
   authenticated; the issue number is really a PR number (very common — `(#N)` squash subjects
   are PR numbers); issue not found / private / rate-limited; unparseable JSON. In every case
   fall back to the commit-message statement with the EXISTING
   `statement from commit message (weaker than issue text)` label plus a note naming what
   failed. A task must never end up with an empty or invented statement.
4. Surface the outcome so a user can weigh it: the plan card reports how many tasks got
   `statement_source: issue` vs `commit-message`, as a label when any enrichment was attempted
   (e.g. `gh enrichment: N/M task(s) used real issue text`). This is the number that says
   whether the leak mitigation actually worked on this repo — it must be visible before spend,
   not buried.
5. **Tests stub `gh` exclusively — no test, verify command, or demo may invoke a real `gh`.**
   That fence is absolute (GUARDRAILS). Cover: success (statement_source becomes `issue`,
   label absent); each degradation path above (fallback + note + label retained); that
   `--with-gh` unset never constructs or calls a runner (spy asserting zero calls); and that
   `default_gh_runner` is not wired as any parameter default (assert via `inspect.signature`).
6. Update `skills/repo-bench/SKILL.md`: document `--with-gh`, state plainly that it requires
   `gh` installed and authenticated and makes one API call per issue-referencing task, and —
   importantly — explain WHY it exists: on repos that squash-merge PR descriptions, the commit
   message can describe the fix, so `statement_source: commit-message` is a signal to weigh the
   verdict more cautiously. Do not overclaim: `--with-gh` cannot help when `(#N)` is a PR
   number with no underlying issue.

**Do NOT** make `--with-gh` a default, give `gh_runner` a subprocess default, invoke a real
`gh` from any test/verify/demo, or touch a reused module.

**Acceptance:** `--with-gh` reaches the existing seam from `plan` and `run`; unset is
byte-identical to today; every failure degrades to the labelled commit-message fallback with a
note; the plan card reports the enrichment ratio; no test invokes a real `gh`; suite green and
only grows.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest discover -s tests -p 'test_repo_bench.py' -q
python3 bin/repo_bench.py plan --help 2>&1 | grep -q -- '--with-gh'
python3 bin/repo_bench.py run --help 2>&1 | grep -q -- '--with-gh'
python3 - <<'PY'
import importlib.util, inspect
spec = importlib.util.spec_from_file_location("repo_bench", "bin/repo_bench.py")
rb = importlib.util.module_from_spec(spec); spec.loader.exec_module(rb)
assert callable(rb.default_gh_runner), "no runtime gh runner"
# the library must NEVER default to a real gh
for fn in (rb.mine_issue_tasks, rb.build_plan):
    d = inspect.signature(fn).parameters["gh_runner"].default
    assert d is None, f"{fn.__name__} defaults gh_runner to {d!r} — a real gh is reachable unset"
assert inspect.signature(rb.mine_issue_tasks).parameters["use_gh"].default is False
src = open("bin/repo_bench.py").read()
assert "gh_runner=default_gh_runner" not in src.replace(" ", ""), "gh runner wired as a default"
print("T14 probe OK")
PY
grep -q -- '--with-gh' skills/repo-bench/SKILL.md
echo "=== no test may reach a real gh ==="
grep -nE 'subprocess[^\n]*"gh"|default_gh_runner' tests/test_repo_bench.py && exit 1 || echo "clean"
git diff --quiet bin/claude_execute.py bin/cost_report.py bin/routing_scorecard.py bin/bench_routing.py
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T13 — `--exclude-subject`: keep bot/chore commits out of the mined task set
- status: done
- model: sonnet
- depends: T12R

**Added by execute AFTER the kit was signed off**, from the first real `plan` against a live
repo (microsoft/pyright). Not a defect in a prior task — a capability nobody knew was needed
until real history was mined.

**Files:** `bin/repo_bench.py`; `tests/test_repo_bench.py` (extend).

**Why:** `ISSUE_REF_RE`'s squash-merge branch matches ANY subject ending `(#N)`, and on a repo
that squash-merges Dependabot, that includes dependency bumps. Measured on pyright's last 400
commits with `--limit 10`: 4 of the 10 mined tasks were
`Bump brace-expansion from 5.0.6 to 5.0.8 (#11569)` and friends. They are correctly
`oracle_tests_available=False`, so the D7 floor keeps them out of the verdict — but they are
still DISPATCHED and JUDGE-GRADED, which on that plan was ~$2.28 of a $13.14 total spent
asking three models to "fix" a version bump.

**Do:**
1. Add `exclude_subject=()` to `mine_issue_tasks` — an iterable of regex strings, compiled
   case-INsensitively, matched with `re.search` against the commit SUBJECT (first line) only.
   Default empty: **absent means today's behavior, exactly.** This is opt-in; do NOT ship a
   built-in default pattern list. Silently dropping commits the user did not ask to drop is
   the same failure class this kit spent four reviews on.
2. Every excluded commit appends a note naming what was dropped and why, e.g.
   `commit <sha7> excluded by --exclude-subject '<pattern>': <subject>`. Exclusions must be
   VISIBLE — a task set that silently shrank reads as "this repo has little history" when it
   actually means "we filtered it".
3. When any exclusion fired, `build_plan` promotes a summary into the plan card's `labels`
   (the same posture `partial coverage` already uses), e.g.
   `N commit(s) excluded by --exclude-subject`.
4. Wire `--exclude-subject` (repeatable, `action="append"`) into the SHARED mining args so both
   `plan` and `run` accept it, and thread it through `build_plan`.
5. Tests: a fixture repo whose history contains a `Bump dep from 1.0 to 1.1 (#9)` commit and a
   real `fixes #7` commit — assert that with `exclude_subject=(r"^Bump ",)` only the real fix
   is mined, a note names the excluded commit, and the plan card carries the summary label;
   assert that with the default (no patterns) BOTH are mined, i.e. today's behavior is
   unchanged; assert an invalid regex is refused with a plain sentence rather than a traceback.

**Do NOT** change `ISSUE_REF_RE`, add a built-in default pattern, touch a reused module, or
alter any existing mining behavior when `exclude_subject` is empty.

**Acceptance:** exclusions are opt-in, visible in notes and labels, and absent-by-default
leaves mining byte-identical to today; suite green and only grows.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest discover -s tests -p 'test_repo_bench.py' -q
python3 - <<'PY'
import importlib.util, inspect, subprocess, sys, tempfile
from pathlib import Path
spec = importlib.util.spec_from_file_location("repo_bench", "bin/repo_bench.py")
rb = importlib.util.module_from_spec(spec); spec.loader.exec_module(rb)
assert "exclude_subject" in inspect.signature(rb.mine_issue_tasks).parameters
with tempfile.TemporaryDirectory() as td:
    repo = Path(td) / "r"; repo.mkdir()
    def g(*a): subprocess.run(["git","-C",str(repo),"-c","user.name=t",
        "-c","user.email=t@example.com",*a], check=True, capture_output=True)
    g("init"); (repo/"m.py").write_text("x=1\n"); g("add","-A"); g("commit","-m","start")
    (repo/"m.py").write_text("x=2\n"); t=repo/"tests"; t.mkdir()
    (t/"test_m.py").write_text("import m\n"); g("add","-A"); g("commit","-m","fixes #7: real fix")
    (repo/"pkg.json").write_text("{}\n"); g("add","-A")
    g("commit","-m","Bump brace-expansion from 5.0.6 to 5.0.8 (#99)")
    both, _ = rb.mine_issue_tasks(repo, gh_runner=None)
    assert len(both) == 2, f"default must mine both, got {len(both)}"
    only, notes = rb.mine_issue_tasks(repo, gh_runner=None, exclude_subject=(r"^Bump ",))
    assert len(only) == 1, f"exclusion failed, got {[t['task_id'] for t in only]}"
    assert only[0]["issue"] == 7, only[0]
    assert any("exclude" in n.lower() for n in notes), notes
print("T13 probe OK")
PY
git diff --quiet bin/claude_execute.py bin/cost_report.py bin/routing_scorecard.py bin/bench_routing.py
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

## Phase 4 — Verdicts, apply, and the surface

### T8 — `verdict`: explicit combination, evidence floor, three-legs reconciliation, full demo
- status: done
- model: opus
- depends: T7

**Files:** `bin/repo_bench.py`; `tests/test_repo_bench.py` (extend).

**Why:** D5/D7/D10 — the credibility core: an inspectable rule instead of a magic score, a
floor that refuses routing-grade claims on thin evidence, and disagreement between the three
legs surfaced instead of averaged.

**Do:**
1. `build_verdict(run_dir, goal, pricing, benchmarks_path=None, kits_dir=None) -> card`.
   Per candidate, from `results.json`: `objective_n` (cells with an AVAILABLE tests
   oracle), `solved_n` (oracle-a passes — the ONLY source of "solved", R6), judge summary
   (grades distribution; `n/a` where None), structural medians (labeled similarity), cost
   (`usd` total + basis) and latency (median wall_seconds), skipped cells. THE RULE,
   rendered into the card as text so it is inspectable: (i) capability order = solved_n/
   objective_n (counts shown, not just rates — small N); ties broken by judge
   `correct`-count, annotated `"tiebreak: judge (subjective)"`; (ii) tier map for
   `goal=tiers`: capability order → `strong`/`mid`/`weak` (more candidates than tiers →
   nearest neighbors listed; fewer → unfilled slots stay empty with a note), with role
   gloss `strong≈reviewer, mid≈implementer, weak≈verifier`; (iii) `goal=daily-driver`:
   among candidates whose solved-count on XS/S-profile tasks is within 1 task of the best,
   pick lowest median (usd, wall_seconds) lexicographic — the applied rule prints with the
   numbers.
2. Evidence floor (D7): `min_tasks = max(MIN_EVIDENCE_TASKS, --min-tasks)` — the flag can
   only raise. Any candidate with `objective_n < min_tasks` ⇒ the CARD (not just the
   candidate) is stamped `below_floor: true` + label `"BELOW EVIDENCE FLOOR — not a
   routing-grade verdict (need >= <n> objectively-scored tasks per candidate)"`; the
   measurement table still renders. Oracle gaps per task render as explicit `n/a` cells —
   grep-able, never dropped rows.
3. Three legs (D10): lazy-load `bench_routing` as `br` and `routing_scorecard` as `rs`.
   Published: `br.load_benchmarks(...)` (default path `PLUGIN_ROOT/"data"/
   "benchmarks.aa.json"`, injectable for tests) + `br.normalize_id` join; absent entry →
   `"no published entry"`. Observed: only when `kits_dir` given and exists —
   `rs.scan_kits`-based per-tier first-try stats for the candidate's tier (reuse, never
   re-parse); else `"no ledger evidence"`. Measured: this run. When published index order
   inverts measured capability order for any candidate pair → note `"DISAGREEMENT — signal,
   not error: published index ranks X above Y; this repo's measurement ranks Y above X"`.
   Never merge the three into one number.
4. `cmd_verdict --run <id> [--goal tiers|daily-driver|both] [--json]`: renders `verdict.md`
   into the run dir (and stdout) — sections: measurement table (one oracle per column,
   `n/a` cells), the rule as applied, the verdict(s), three-legs table, labels, spend
   summary. Also folds verdict + labels back into `results.json` under `"verdict"`
   (rewrite via json — still the one writer).
5. `demo` finale: extend to the FULL pipeline — fixture repo, stub dispatch runner (one
   candidate solves via the stub writing the fixing change, one does not), stub judge
   output, verdict rendered — assert-printed proof lines including the below-floor stamp
   (the demo's 1–2 tasks are deliberately below floor: the demo itself demonstrates the
   refusal honestly). Everything in a temp dir; exit 0.
6. Tests: solved-only-from-tests (a cell with judge `correct` but tests failed is NOT
   solved); floor stamping at `objective_n < 5` and clean at ≥ 5 (synthetic results.json
   fixtures — build cells directly); `--min-tasks 3` still floors at 5; daily-driver rule
   on hand-built numbers (cheap-and-close wins; a clearly-worse-capability candidate never
   picked); disagreement note fires on an inverted synthetic benchmark fixture; `n/a`
   rendering; verdict.md written under the run dir only.

**Acceptance:** no blended scalar anywhere; the applied rule is printed beside its result;
below-floor verdicts are loudly stamped; the three legs stand side by side with
disagreement named; demo covers the whole pipeline honestly; suite green.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest discover -s tests -p 'test_repo_bench.py' -q
python3 bin/repo_bench.py demo > /tmp/repo_bench_t8_demo.txt
grep -q "BELOW EVIDENCE FLOOR" /tmp/repo_bench_t8_demo.txt
grep -qi "similarity" /tmp/repo_bench_t8_demo.txt
python3 - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location("repo_bench", "bin/repo_bench.py")
rb = importlib.util.module_from_spec(spec); spec.loader.exec_module(rb)
assert rb.MIN_EVIDENCE_TASKS == 5
src = open("bin/repo_bench.py").read()
for fn in ("load_benchmarks", "normalize_id"):
    assert f"br.{fn}" in src, f"bench_routing.{fn} not reused"
assert "scan_kits" in src, "routing_scorecard ledger reuse missing"
print("T8 probe OK")
PY
git diff --quiet bin/claude_execute.py bin/cost_report.py bin/routing_scorecard.py bin/bench_routing.py
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T9 — `apply` + `list`: opt-in prefs write, staleness-guarded
- status: done
- model: sonnet
- depends: T8

**Files:** `bin/repo_bench.py`; `tests/test_repo_bench.py` (extend).

**Why:** D9 — measurement never changes routing as a side effect; a separate explicit step
does, and only when the evidence clears the floor.

**Do:**
1. `PREFS_SCHEMA_VERSION = 1`, `DEFAULT_PREFS_PATH = PLUGIN_ROOT / "prefs" /
   "repo-bench.json"` (gitignored by the existing root-anchored `/prefs/` line — verify,
   do not re-add). `build_prefs_payload(verdict_card, pricing) -> dict`:
   `{"schema_version": 1, "applied_at": <UTC ISO>, "source_run", "repo", "tiers":
   {"strong": id|None, "mid": ..., "weak": ...}, "daily_driver": id|None, "labels": [...]}`
   — labels LIFTED from the verdict card (below-floor never reaches here; see refusals).
2. `cmd_apply --run <id> [--store-dir] [--prefs-path]`: read the run's `results.json`
   verdict; REFUSE exit 2 with a plain sentence when: no verdict recorded (`run verdict
   first`), `below_floor` true (D7 — `a below-floor verdict is never applied`), or any
   tier/daily-driver id absent from the CURRENT `data/pricing.json` models (staleness:
   `model <id> is no longer in pricing.json — re-run the benchmark`). Otherwise print
   exactly what will be written (old file's tiers when one exists, new tiers, source run),
   write atomically, and confirm. No `--yes` needed — running `apply` IS the explicit
   opt-in; the printout is the receipt.
3. `cmd_list`: extend T1's `list_runs` rendering — per run: id, repo, mode, candidates,
   spend + basis, verdict present?, below-floor?, applied? (compare prefs `source_run`).
   Tolerant per T1; no dollars invented for runs without spend records (show `-`).
4. Tests: synthetic run dirs (hand-built `results.json` — sanctioned: these are FIXTURES
   for the reader, in temp stores, never the real `benchruns/`): apply happy path writes
   the pinned schema to a temp prefs path; all three refusals (no verdict / below floor /
   stale id against a fixture pricing dict); re-apply overwrites with new `applied_at`;
   `list` shows applied marker; `list` tolerance on a rogue run dir.

**Acceptance:** apply is the only routing-state writer, refuses thin or stale evidence, and
prints its receipt; suite green.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest discover -s tests -p 'test_repo_bench.py' -q
grep -qx '/prefs/' .gitignore
python3 - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location("repo_bench", "bin/repo_bench.py")
rb = importlib.util.module_from_spec(spec); spec.loader.exec_module(rb)
assert rb.PREFS_SCHEMA_VERSION == 1
assert rb.DEFAULT_PREFS_PATH.name == "repo-bench.json" and rb.DEFAULT_PREFS_PATH.parent.name == "prefs"
assert callable(getattr(rb, "build_prefs_payload", None)), "build_prefs_payload missing"
print("T9 probe OK")
PY
git diff --quiet bin/claude_execute.py bin/cost_report.py bin/routing_scorecard.py bin/bench_routing.py
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T10 — `.gitignore` + `CLAUDE.md`: the benchruns store becomes repo law
- status: done
- model: haiku
- depends: T1
- independent: yes

**Files:** `.gitignore`; `CLAUDE.md`.

**Why:** D8 — the store must be uncommittable before any real run can ever write it, and
the always-on money/store law belongs beside the memory/telemetry invariants.

**Do:**
1. Append to `.gitignore`, after the `/telemetry/` block, exactly:

   ```
   # repo-bench measurement store (run artifacts, sandboxes, dollar data — never committed)
   /benchruns/
   ```

   The leading slash is load-bearing (root-anchored — precedent: `/telemetry/`).
2. In `CLAUDE.md`, append this bullet to the end of the `## Invariants` list, verbatim:

   ```
   - **`bin/repo_bench.py` measures models on a target repo and can spend real tokens — but
     only behind `--live` plus an explicit `--max-usd` ceiling; `plan`/`demo` and every test
     spend nothing.** Tests stub every dispatch and `gh` runner and use fixture repos in temp
     dirs. Target repos are read-only by construction (allowlisted git commands; sandboxes
     are history-free tree extractions). Its store (`benchruns/`, gitignored) is written by
     `bin/repo_bench.py` only — never hand-authored or backdated; verdicts below the evidence
     floor are never applied, and routing changes only via the explicit `apply` step writing
     gitignored `prefs/repo-bench.json`.
   ```

3. In `CLAUDE.md`'s `## How to run things` code block, after the
   `python3 bin/telemetry_snapshot.py --list` line, add exactly:

   ```
   python3 bin/repo_bench.py demo                  # repo-bench full-pipeline smoke: fixture repo, stub dispatch, all four oracles, below-floor verdict honesty — no network, no spend (lands with the repo-bench kit)
   python3 bin/repo_bench.py plan --repo . --models sonnet,haiku   # priced models×tasks matrix for a repo, from pricing.json — prints the ceiling and stops; only `run --live --max-usd` ever spends
   ```

4. Change nothing else in either file.

**Acceptance:** both files carry the exact text; CLAUDE.md ≤ 16000 bytes; layout test green.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
grep -qx '/benchruns/' .gitignore
grep -q 'repo-bench measurement store' .gitignore
grep -q 'behind `--live` plus an explicit `--max-usd` ceiling' CLAUDE.md
grep -q 'bin/repo_bench.py demo' CLAUDE.md
python3 - <<'PY'
from pathlib import Path
size = Path("CLAUDE.md").stat().st_size
assert size <= 16000, f"CLAUDE.md is {size} bytes"
text = Path("CLAUDE.md").read_text()
assert text.count("repo_bench.py") >= 3
print("T10 probe OK")
PY
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T11 — NEW `skills/repo-bench/SKILL.md`: the user-facing surface
- status: done
- model: sonnet
- depends: T9
- independent: yes

**Files:** NEW `skills/repo-bench/SKILL.md`.

**Why:** the engine is only reachable through a skill; the skill must carry the plan-first
posture and the honesty rules into every session that uses it.

**Do:**
1. YAML frontmatter: `name: repo-bench`; `description:` triggering on "benchmark models on
   my repo", "which model should implement/review in this repo", "re-tier / re-classify
   models for this project", "find a daily driver model", "measure model X on our codebase"
   — and stating that the default is a priced plan, never a spend. `allowed-tools: Bash,
   Read` (the `bench-routing` frontmatter is the house pattern).
2. Body, modeled on `skills/bench-routing/SKILL.md`: the `${CLAUDE_PLUGIN_ROOT}` resolution
   paragraph verbatim in shape (fallback: resolve `../../bin/repo_bench.py` relative to this
   SKILL.md to an absolute path before shelling out); run-line block for `plan`, `run`,
   `verdict`, `apply`, `list`, `demo`.
3. Subcommand documentation (derive wording from PLAN.md D1–D11 — no prices, no model ids):
   plan-first law (NEVER add `--live` yourself: present the plan and its total, and only run
   live after the user explicitly confirms the ceiling in THIS conversation); the two
   acquisition modes and when each engages; the four oracles with their labels and the rule
   that `solved` is tests-only; the evidence floor (verdicts below it are presented AS
   below-floor, never softened); the three-legs presentation rule (lead with the measured
   verdict, show published prior + ledger beside it, name disagreement as signal, never
   average); apply is a separate explicit user action — never chain `run` into `apply`; the
   D11 exposure sentence (only benchmark repos whose test suite you would run by hand).
4. Presenting-results section: quote labels verbatim (`similarity … NOT a correctness
   verdict`, `BELOW EVIDENCE FLOOR`, `partial (cost-ceiling)`, spend basis); never present
   an estimate as a bill; state per-verdict oracle coverage.

**Acceptance:** frontmatter valid and description trigger-rich; body carries every rule in
step 3–4; no hardcoded price or model id anywhere in the file.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 - <<'PY'
from pathlib import Path
text = Path("skills/repo-bench/SKILL.md").read_text()
head = text.split("---")[1]
assert "name: repo-bench" in head
assert "allowed-tools:" in head
for token in ("${CLAUDE_PLUGIN_ROOT}", "--live", "--max-usd", "BELOW EVIDENCE FLOOR",
              "apply", "DISAGREEMENT", "daily driver"):
    assert token in text, token
assert "claude-fable" not in text and "claude-opus" not in text and "claude-sonnet" not in text
assert "$10" not in text and "$5" not in text  # no literal prices
print("T11 probe OK")
PY
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T12R — Phase 4 remediation: the forgeable harness, the null-clobber apply, and three false claims
- status: done
- model: opus
- depends: T12

**Added by execute** after the Phase 4 review: 9 findings, all 9 adjudicated real. F1 blocks
sign-off; the reviewer's stated verdict is "not yet complete."

**Files:** `bin/repo_bench.py`; `tests/test_repo_bench.py`; `skills/repo-bench/SKILL.md`.

**Do:**

1. **F1 (BLOCKING) — `solved` is forgeable via the test HARNESS.** `oracle_tests` restores and
   deletes only paths matching `DEFAULT_TEST_PATTERNS`. The file `--test-cmd` actually invokes
   usually matches none of them — verified against the real constant: `conftest.py`,
   `run_tests.py`, `Makefile`, `pyproject.toml`, `tox.ini`, `pytest.ini`, `setup.py`,
   `noxfile.py` are ALL `False`. Reproduced end to end: a stub candidate that touched no module
   and no test-pattern path, and only rewrote `run_tests.py` to `import sys; sys.exit(0)`,
   earned `passed=True` on 6/6 cells, cleared the D7 floor, and was APPLIED to a prefs file at
   exit 0 — with `candidate_touched_tests` empty, so T7R's visibility net missed it.
   Note the oracle's docstring claims a candidate-authored `conftest.py` is in the closed
   class. It is not. Fix the docstring too — a false safety claim is its own defect.
   **The fix must be structural, not another pattern list**, and it must be a WHITELIST, not a
   blacklist. A pattern list describes NAMES; the oracle consists of whatever `--test-cmd`
   executes at run time. Reverting "the bad parts" of the candidate's tree is the same shape as
   the three fixes that already failed — it requires correctly enumerating what to take away.

   **THE INVARIANT (write it down, then satisfy it structurally):**

       the grade result is a function of
           (base tree, the candidate's IN-SCOPE patch, the reference test blobs)
       and nothing else.

   So do not grade the candidate's tree at all. CONSTRUCT the grade substrate from known-good
   pieces: a fresh copy of the BASE tree, plus only the candidate's hunks for paths inside the
   reference patch's scope, plus the reference `test_blobs`. Nothing the candidate wrote
   outside that scope can be present, because it was never applied — no enumeration of harness
   files, config files, dotfiles, planted `sitecustomize.py`, new files, or symlinks is
   required, and none has to be anticipated.

   Record the candidate's out-of-scope paths on the cell (e.g.
   `candidate_modified_out_of_scope`) and surface them in the verdict the way
   `candidate_touched_tests` is surfaced — they are still evidence, they just no longer reach
   the substrate.

   **Prove the construction, not the outcomes.** Add a PROPERTY test asserting the grade
   substrate is byte-identical to that constructed triple, plus a PARAMETERIZED adversarial
   test over a list that includes at minimum: the `--test-cmd` entry point, `conftest.py`,
   `Makefile`, `tox.ini`, `pytest.ini`, `setup.py`, `pyproject.toml`, a root `sitecustomize.py`,
   a brand-new file, and a dotfile — asserting NONE of them can change the grade. A case test
   proves one hole is closed; the property test proves the class is.
   **State the tradeoff honestly rather than hiding it:** a candidate that legitimately fixes
   the bug in a file the reference patch did not touch will have that change reverted and the
   cell will read `not solved`. That is a FALSE NEGATIVE, and it must be VISIBLE — the cell
   carries the out-of-scope paths and a note, so a user can see why it failed rather than
   being told the model is worse than it is. A visible false negative is acceptable; an
   invisible false positive is not, because only one of them can silently re-route real work.
   Tests: reproduce the reviewer's forgery (candidate rewrites the `--test-cmd` entry point,
   touching no test-pattern path) and assert it is NOT solved and IS recorded; assert a
   genuine in-scope fix still solves; assert the false-negative case is labelled, not silent.
2. **F3 — `apply` writes an all-`None` tier map over a good one, and this is engine-producible.**
   `build_prefs_payload` reads `slots.get(slot)`, so a card yielding zero ids applies
   successfully and erases an existing prefs file. Not hand-edit-only: `verdict --goal
   daily-driver` sets `tier_map: None`, and `_daily_driver` legitimately returns `pick: None`
   when no candidate is eligible-and-priced — so `apply` on such a run reports success and
   wipes a previously good tier map. Fix: refuse when the payload would name NO model at all,
   and do not let a goal-scoped verdict silently clear slots it never measured (either merge
   with the existing file for unmeasured slots, or refuse and say why — pick one and state the
   rationale). Also: a non-string slot value currently raises `AttributeError` out of
   `cost_report.match_model`, escaping `main`'s handler as a traceback — refuse with the same
   plain sentence its sibling cases use.
3. **F2 — the demo never exercises general (mutation-repair) mode**, but PLAN's Done-means
   clause 1 says "both acquisition modes exercised" and `skills/repo-bench/SKILL.md` tells the
   user the demo covers both. `cmd_demo` hardcodes `--mode issue-replay`. The capability is
   real and unit-tested; only its own acceptance surface omits it. Extend the demo to exercise
   general mode too (keep it fully synthetic, temp-dir only, no spend), so the clause is true.
4. **F4 — `verdict --json` does not emit valid JSON.** It prints a blank line and
   `verdict.md: <path>` after the JSON body, so `json.loads` fails with `Extra data`. `plan
   --json` and `list --json` both parse. Send the path line to stderr (or omit it under
   `--json`) so the documented "machine-readable output" actually is.
5. **F5–F7 — three skill claims that are not the engine's behavior.** Fix in
   `skills/repo-bench/SKILL.md`: (a) it calls structural similarity "always available", but the
   engine has an explicit `available: False` channel — a user told "always available" cannot
   interpret an `n/a` there; (b) it instructs quoting `judge: unparseable` verbatim, a string
   that appears nowhere in the engine (the rendered cell is `n/a (unparseable)`); (c) it says a
   spendless run shows `-`, but `_format_spend_cell` renders `n/a`.
6. **F8 — sharpen one disclosure.** The skill gives the judge-cwd rationale as "ancestry clues
   (which sandbox belongs to which candidate, dispatch order)". The engine's real reason is
   stronger: `../../tasks/<id>.json` holds the reference patch and the withheld test blobs —
   i.e. the answer to "which slot is the reference". State the real reason.
7. **F9 — general mining silently returns fewer tasks than `--limit`** unless the examine bound
   was hit (asked for 3, got 1, no note). Add the note.

**Do NOT** weaken any existing leak or forgery assertion, widen `READ_ONLY_GIT`, touch a reused
module, or change what T2/T3 mine.

**Acceptance:** a candidate that rewrites the `--test-cmd` entry point cannot be `solved`, and
out-of-scope modifications are recorded and surfaced; the false-negative tradeoff is visible on
the cell; `apply` never writes a payload naming no model and never silently clears unmeasured
slots; the demo exercises both acquisition modes; `verdict --json` parses; the skill's claims
match the engine; suite green and only grows.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m unittest discover -s tests -p 'test_repo_bench.py' -q
python3 bin/repo_bench.py demo > /tmp/rb_t12r_demo.txt
grep -q "BELOW EVIDENCE FLOOR" /tmp/rb_t12r_demo.txt
grep -qiE "general|mutation" /tmp/rb_t12r_demo.txt
python3 - <<'PY'
import importlib.util, json, subprocess, sys
spec = importlib.util.spec_from_file_location("repo_bench", "bin/repo_bench.py")
rb = importlib.util.module_from_spec(spec); spec.loader.exec_module(rb)
src = open("bin/repo_bench.py").read()
assert "candidate_modified_out_of_scope" in src, "out-of-scope tracking missing (F1)"
skill = open("skills/repo-bench/SKILL.md").read()
assert "always available" not in skill, "skill still claims structural is always available (F5)"
assert "judge: unparseable" not in skill, "skill still quotes a string the engine never emits (F6)"
print("T12R probe OK")
PY
git diff --quiet bin/claude_execute.py bin/cost_report.py bin/routing_scorecard.py bin/bench_routing.py
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```

### T12 — `skills/route/SKILL.md`: the pull-only prefs pointer
- status: done
- model: haiku
- depends: T9
- independent: yes

**Files:** `skills/route/SKILL.md` (body only — YAML frontmatter untouched).

**Why:** D9 — the measured tier map is only useful if the router knows to look; consumption
stays pull-only and advisory, so this is one paragraph, not a code change.

**Do:**
1. At the END of the SKILL.md body (after the last existing section), append exactly:

   ```
   ## Measured tier map (repo-bench, optional)

   Before recommending, check for `${CLAUDE_PLUGIN_ROOT}/prefs/repo-bench.json` (gitignored;
   written only by an explicit `repo_bench.py apply` after a measured benchmark run). If it
   exists and its `repo` matches the project being routed for, prefer its `tiers` /
   `daily_driver` model ids over the default tier picks and SAY SO, citing `source_run` and
   `applied_at`. If any id in it is missing from `data/pricing.json`, ignore the file and
   say it is stale. Absent file = no change to this skill's behavior.
   ```

2. Change nothing else in the file; frontmatter and all existing sections stay
   byte-identical.

**Acceptance:** the paragraph is present at the end, frontmatter untouched, no other diff
in the file.

**Verify:**
```bash
cd "$(git rev-parse --show-toplevel)"
python3 - <<'PY'
from pathlib import Path
text = Path("skills/route/SKILL.md").read_text()
head = text.split("---")[1]
assert "repo-bench" not in head, "frontmatter was touched"
i = text.index("## Measured tier map (repo-bench, optional)")
assert "prefs/repo-bench.json" in text[i:]
assert "say it is stale" in text[i:]
assert text.rstrip().endswith("behavior.") or "Absent file" in text[i:]
print("T12 probe OK")
PY
git diff --stat skills/route/SKILL.md > /tmp/repo_bench_t12_diff.txt
python3 - <<'PY'
from pathlib import Path
stat = Path("/tmp/repo_bench_t12_diff.txt").read_text()
assert "skills/route/SKILL.md" in stat, stat
print("T12 diff-scope OK")
PY
python3 -m unittest discover -s tests -q
python3 -m unittest discover -s tests -p 'test_guardrails_layout.py' -q
```
