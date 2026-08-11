#!/usr/bin/env python3
"""repo_bench — measure candidate Claude models on a chosen repo's own work.

Three laws govern this module. They are structural, not stylistic: a change that "works"
while weakening one of them is a wrong change.

MONEY / NETWORK LAW
    Nothing here spends money or touches the network by default. Real model dispatch is
    reachable only from `run` behind BOTH `--live` AND an explicit `--max-usd` ceiling, and
    the ceiling is re-checked before EVERY dispatch (judge grades included). Every dispatch
    -- and every optional `gh` enrichment -- goes through an INJECTABLE runner callable;
    tests stub every one of them and never invoke the real `claude`/`gh` CLI. `plan`, `demo`
    and stub runners are the only sanctioned smokes. `subprocess` to local `git` is
    sanctioned (free, offline) and, for a TARGET repo, restricted by the allowlist below.
    A `--max-usd` ceiling is trusted only after `validate_ceiling()` -- `nan`/`inf`/negative
    values parse cleanly through argparse's `type=float` yet defeat every downstream `>`
    comparison (`x > nan` is always False), so THAT is the one place the ceiling is checked
    for sanity; every per-dispatch re-check (here and in `run`'s loop) must call it rather
    than re-deriving the check.

TARGET-REPO READ-ONLY LAW
    A benchmarked repo is read-only BY CONSTRUCTION. `git_target()` is the single choke
    point for touching a target and it accepts only the `READ_ONLY_GIT` verbs; every other
    git call in this module runs against a sandbox we built ourselves, through
    `git_sandbox()`. Sandboxes are history-free tree extractions (`git archive` -> tar ->
    fresh `git init`), never a `git worktree` (shares refs/objects with the user's checkout)
    and never a `git clone` (the reference fix and origin refs ride along -- a solution
    leak). See PLAN D3.

STORE LAW
    `bin/repo_bench.py` is the ONLY writer under a benchruns store. Envelopes are never
    hand-authored, never backdated, and always carry their own honesty labels; the run id
    is content-free (`claude_execute.generate_run_id()`), and the store reader degrades with
    notes rather than crashing on a store that is absent or has rogue entries. See PLAN D8.

SETUP-PATCH LAW (general / mutation-repair mode)
    A general-mode task's bug does not exist in the target's history -- `mine_general_tasks`
    injects it into a THROWAWAY scratch sandbox and then throws that sandbox away. So a
    candidate's sandbox, built fresh off `base_commit`, is GREEN: the repo passes its own
    tests and the task's statement ("the test suite fails") is a lie. Every task record
    therefore carries `setup_patch`: the FORWARD mutation diff (original -> mutated),
    git-`apply`-able to a fresh sandbox off `base_commit`.

    ANY DISPATCH PATH MUST APPLY `setup_patch` TO THE CANDIDATE'S SANDBOX BEFORE DISPATCH
    WHENEVER IT IS NOT None -- otherwise the candidate is told the suite fails and handed a
    passing repo, and the whole measurement is vacuous. Issue-replay records carry
    `setup_patch: None` on purpose: their `base_commit` is already the buggy state.
    `setup_patch` is NOT a solution hint -- it is the bug -- and it is the exact inverse of
    `reference_patch`, which never reaches a candidate. It must be AMENDED INTO the sandbox's
    root commit, never committed on top of it: a second commit turns the candidate's own
    `git log -p` into the answer key (`git diff HEAD~1 HEAD`, reversed, IS the fix).

Usage:
  repo_bench.py list [--store-dir DIR]
  repo_bench.py demo
  repo_bench.py plan --repo DIR --models m1,m2 [--mode auto|issue-replay|general]
                      [--limit N] [--test-cmd CMD] [--setup-cmd CMD] [--setup-key PATH]
                      [--judge MODEL] [--commit SHA] [--store-dir DIR] [--json]
  repo_bench.py run --repo DIR --models m1,m2 [same mining flags as plan]
                     [--store-dir DIR] [--live --max-usd CEILING]
  repo_bench.py verdict --run RUN_ID [--store-dir DIR] [--goal tiers|daily-driver|both]
                     [--min-tasks N] [--benchmarks PATH] [--kits-dir DIR] [--json]
  (apply lands in a later task)
"""

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import weakref
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------------------------
# Reuse, never re-implement (the `_load` importlib pattern from bin/bench_routing.py).

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, PLUGIN_ROOT / "bin" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_CE_MOD = None
_CR_MOD = None
_BR_MOD = None
_RS_MOD = None


def _ce():
    """Lazy handle on bin/claude_execute.py (`generate_run_id`, argv shape, resolvers).

    Lazy so that importing this module -- which tests do constantly -- costs nothing and so
    that a store-only command never drags the dispatch machinery in.
    """
    global _CE_MOD
    if _CE_MOD is None:
        _CE_MOD = _load("claude_execute")
    return _CE_MOD


def _cr():
    """Lazy handle on bin/cost_report.py -- the pricing loader (`PRICING_PATH`,
    `load_pricing`) and the rate math (`match_model`, `rates_for`).

    Reuse, never fork: `data/pricing.json` is the single numeric source of truth and
    `cost_report` already owns the one path to it. This module never re-derives that path
    and never parses that file itself.
    """
    global _CR_MOD
    if _CR_MOD is None:
        _CR_MOD = _load("cost_report")
    return _CR_MOD


def _br():
    """Lazy handle on bin/bench_routing.py -- the PUBLISHED leg of PLAN D10.

    `load_benchmarks` (the reader for `data/benchmarks.aa.json`), `normalize_id` (the
    dash/dot fold that makes the id join correct) and `claude_tier_for_model` (the pricing
    join that resolves a candidate's tier) all live there. This module re-implements none of
    them: a second benchmark reader, a second id normaliser or a second model->tier table is
    a fork of the sharpest fence in the kit (PLAN D10/R4).
    """
    global _BR_MOD
    if _BR_MOD is None:
        _BR_MOD = _load("bench_routing")
    return _BR_MOD


def _rs():
    """Lazy handle on bin/routing_scorecard.py -- the OBSERVED leg of PLAN D10.

    `scan_kits` + `history_tier_stats` are the ledger parser and the per-tier first-try
    statistics. This module never re-parses a `NOTES.md` ledger line itself; it reads what
    the scorecard already produces. Lazy for the same reason `_ce`/`_cr` are: a `plan`, a
    `run` or a `list` must not drag the ledger machinery in.
    """
    global _RS_MOD
    if _RS_MOD is None:
        _RS_MOD = _load("routing_scorecard")
    return _RS_MOD


# ---------------------------------------------------------------------------------------------
# Sanctioned structural constants. Never a price, price ratio, pricing date, or model id --
# those all resolve from data/pricing.json at run time.

STORE_SCHEMA_VERSION = 1

DEFAULT_STORE_DIR = PLUGIN_ROOT / "benchruns"

#: PLAN D9: the ONE routing-state writer in this module. `/prefs/` is already gitignored
#: (root-anchored, same line the `copilot_prefs` precedent uses) -- this file never re-adds
#: it. `PREFS_SCHEMA_VERSION` is pinned independently of `STORE_SCHEMA_VERSION`: the run
#: store and the applied-prefs file are different artifacts with different writers and no
#: reason to version together.
PREFS_SCHEMA_VERSION = 1
DEFAULT_PREFS_PATH = PLUGIN_ROOT / "prefs" / "repo-bench.json"

#: Evidence floor (PLAN D7): objectively-scored tasks per candidate a routing-grade verdict
#: needs. Defined ONCE, here, module-level -- T4/T8 (and `choose_mode` below) all consume
#: this one constant; never a second copy or a re-derived value.
MIN_EVIDENCE_TASKS = 5

#: The complete `statement_source` vocabulary a mined task record may carry. Pinned so a
#: renderer (T8) is written against the real vocabulary rather than a guessed pair:
#:   "issue"           -- the target's own issue text, via the optional `gh` enrichment
#:   "commit-message"  -- the fix commit's subject+body (weaker; always labelled as such)
#:   "generated"       -- a synthetic general-mode statement this module wrote itself
#: Every emitted record is checked against this tuple; a new source means adding it HERE.
STATEMENT_SOURCES = ("issue", "commit-message", "generated")

#: The pinned task-record key set -- BOTH miners emit exactly these keys, so every consumer
#: (prompt builder, dispatcher, oracles, judge, renderer) can read any field of any task
#: without a mode check. Fields a mode cannot fill carry None (issue-replay: `setup_patch`;
#: general: `issue`, `fix_commit`), never absence. Widening this is a schema change: update
#: both miners and the parity test together, never one alone.
TASK_RECORD_KEYS = frozenset({
    "task_id", "mode", "issue", "base_commit", "fix_commit", "subject", "statement",
    "statement_source", "reference_patch", "setup_patch", "test_blobs",
    "oracle_tests_available", "size_profile", "labels", "notes",
})

#: The read-only git allowlist (PLAN D3). The ONLY verbs `git_target` will run against a
#: benchmarked repo. Widening this is forbidden -- a target repo must stay byte-identical.
READ_ONLY_GIT = ("archive", "show", "log", "rev-parse", "diff", "ls-tree", "cat-file", "status")

#: Config pinned onto every sandbox git call: identity so `commit` works on any machine
#: (never inheriting the user's), and a branch name so `init` is quiet and nothing in this
#: module ever depends on the ambient default branch name.
SANDBOX_GIT_CONFIG = (
    "-c", "user.name=repo-bench",
    "-c", "user.email=repo-bench@localhost",
    "-c", "init.defaultBranch=bench",
    "-c", "commit.gpgsign=false",
)

#: T5R2: config PERSISTED into every sandbox's own `.git/config` (not `-c`, which would bind
#: only the commands this module runs). A repo-bench sandbox is history-free by construction
#: (PLAN D3) and these two keys are what make the candidate's `git` agree:
#:
#:   * `core.logAllRefUpdates=false` -- no reflog is ever written, so a general-mode candidate
#:     cannot recover the injected bug with `git diff HEAD@{1} HEAD` after the setup patch is
#:     amended into the root commit. A reflog IS history to mine.
#:   * `log.showRoot=false` -- `git log -p` shows the root commit as a big creation event by
#:     default, i.e. the entire tree as one `+`-diff. That reveals nothing a candidate cannot
#:     read with `cat`, but a sandbox whose whole premise is "there is no history here" must
#:     not present a diff at all: the moment it does, the next reader has to reason about
#:     WHICH diff it is rather than knowing there is none.
SANDBOX_LOCAL_CONFIG = (
    ("core.logAllRefUpdates", "false"),
    ("log.showRoot", "false"),
)

SANDBOX_INIT_MESSAGE = "repo-bench sandbox base"


# ---------------------------------------------------------------------------------------------
# git seams


def default_git_runner(argv):
    """Local `git` runner -> (rc, stdout+stderr). Free, offline, no model, no network."""
    proc = subprocess.run(argv, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def git_target(repo, *args, git_runner=None):
    """THE single choke point for touching a TARGET repo. Read-only verbs only (PLAN D3).

    Raises ValueError naming the allowlist for anything else -- including a bare call with
    no verb. Returns (rc, output); callers decide what a non-zero rc means.
    """
    verb = args[0] if args else None
    if verb not in READ_ONLY_GIT:
        raise ValueError(
            f"repo_bench refuses git {verb!r} against a target repo: the read-only allowlist "
            f"is {', '.join(READ_ONLY_GIT)} (PLAN D3 -- target repos are read-only by "
            f"construction; never widen this)"
        )
    runner = git_runner or default_git_runner
    return runner(["git", "-C", str(repo), *args])


def git_sandbox(sandbox, *args, git_runner=None):
    """Git against a sandbox WE built (no allowlist -- the sandbox is ours to mutate)."""
    runner = git_runner or default_git_runner
    return runner(["git", "-C", str(sandbox), *SANDBOX_GIT_CONFIG, *args])


def _require_ok(rc, out, what):
    if rc != 0:
        raise ValueError(f"{what} failed (rc={rc}): {(out or '').strip()}")
    return out


# ---------------------------------------------------------------------------------------------
# Sandbox: tree extraction + fresh `git init` (PLAN D3)


def make_sandbox(target_repo, commit, dest, git_runner=None):
    """Extract `commit`'s TREE from `target_repo` into `dest` as a history-free git repo.

    `git archive` writes a tar of exactly one tree; we extract it with stdlib `tarfile` (no
    shell pipes) and then `git init` + `SANDBOX_LOCAL_CONFIG` + one commit in `dest`. The
    result contains NO target history, so the reference fix is unreachable from inside the
    sandbox by construction -- that is the whole point, not an optimisation. The persisted
    config is part of that construction, not cosmetics: it keeps the sandbox's own git from
    growing a reflog or presenting a root-creation diff, both of which are history to mine.

    Returns {"path", "base_commit", "init_commit"}.
    """
    target_repo = Path(target_repo)
    dest = Path(dest)
    if not target_repo.exists():
        raise FileNotFoundError(f"target repo not found: {target_repo}")

    dest.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="repo-bench-archive-") as tmp:
        tar_path = Path(tmp) / "tree.tar"
        rc, out = git_target(
            target_repo, "archive", "--format=tar", "-o", str(tar_path), str(commit),
            git_runner=git_runner,
        )
        _require_ok(rc, out, f"git archive {commit} from {target_repo}")
        if not tar_path.exists():
            raise ValueError(f"git archive produced no tar for {commit} in {target_repo}")
        with tarfile.open(tar_path) as tf:
            try:
                tf.extractall(dest, filter="data")
            except TypeError:  # pragma: no cover - git-dependent stdlib age
                tf.extractall(dest)

    rc, out = git_sandbox(dest, "init", "-q", git_runner=git_runner)
    _require_ok(rc, out, f"git init in sandbox {dest}")
    # Persisted BEFORE the first commit, so no reflog entry is ever written (T5R2).
    for key, value in SANDBOX_LOCAL_CONFIG:
        rc, out = git_sandbox(dest, "config", key, value, git_runner=git_runner)
        _require_ok(rc, out, f"git config {key} in sandbox {dest}")
    rc, out = git_sandbox(dest, "add", "-A", git_runner=git_runner)
    _require_ok(rc, out, f"git add in sandbox {dest}")
    rc, out = git_sandbox(
        dest, "commit", "--allow-empty", "-q", "-m", SANDBOX_INIT_MESSAGE, git_runner=git_runner
    )
    _require_ok(rc, out, f"git commit in sandbox {dest}")
    rc, out = git_sandbox(dest, "rev-parse", "HEAD", git_runner=git_runner)
    _require_ok(rc, out, f"git rev-parse in sandbox {dest}")

    return {
        "path": str(dest),
        "base_commit": str(commit),
        "init_commit": out.strip(),
    }


def sandbox_init_commit(sandbox, git_runner=None):
    """The sandbox's root commit -- the one `make_sandbox` created.

    Derived (`rev-list --max-parents=0 HEAD`) rather than remembered so a caller holding
    only a path can still capture a patch, and so commits the candidate made cannot move
    the baseline.
    """
    rc, out = git_sandbox(sandbox, "rev-list", "--max-parents=0", "HEAD", git_runner=git_runner)
    _require_ok(rc, out, f"git rev-list in sandbox {sandbox}")
    roots = [line.strip() for line in out.splitlines() if line.strip()]
    if len(roots) != 1:
        raise ValueError(
            f"sandbox {sandbox} has {len(roots)} root commits; expected exactly 1 "
            f"(a repo-bench sandbox is built history-free)"
        )
    return roots[0]


def capture_patch(sandbox, init_commit=None, git_runner=None):
    """The candidate's whole change as a unified diff against the sandbox's initial commit.

    `git add -A` first so brand-new files are included, then diff the INDEX against the
    initial commit: that catches uncommitted edits and changes the candidate committed
    alike, since the index reflects the worktree either way.
    """
    sandbox = Path(sandbox)
    base = init_commit or sandbox_init_commit(sandbox, git_runner=git_runner)
    rc, out = git_sandbox(sandbox, "add", "-A", git_runner=git_runner)
    _require_ok(rc, out, f"git add in sandbox {sandbox}")
    rc, out = git_sandbox(
        sandbox, "diff", "--cached", "--no-color", "--no-ext-diff", base, git_runner=git_runner
    )
    _require_ok(rc, out, f"git diff in sandbox {sandbox}")
    return out


# ---------------------------------------------------------------------------------------------
# Run store (PLAN D8) -- this module is its only writer.

RUN_SUBDIRS = ("tasks", "dispatches", "work")


def new_run_dir(store_dir, now=None):
    """Create `<store>/<run-id>/` with its subdirs and a minimal `meta.json`.

    The run id is `claude_execute.generate_run_id()` -- `<UTC-date>-<4 hex>`, content-free
    (no hostname, user, path fragment). Dated by construction, telemetry's dated-envelope
    spirit at per-run granularity.
    """
    store_dir = Path(store_dir)
    ce = _ce()
    run_id = None
    for _ in range(64):
        candidate = ce.generate_run_id(now=now)
        if not (store_dir / candidate).exists():
            run_id = candidate
            break
    if run_id is None:  # pragma: no cover - 64 collisions is not a reachable state
        raise ValueError(f"could not allocate a free run id under {store_dir}")

    run_path = store_dir / run_id
    for sub in RUN_SUBDIRS:
        (run_path / sub).mkdir(parents=True, exist_ok=True)
    meta = {
        "store_schema_version": STORE_SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(),
    }
    (run_path / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return run_id, run_path


def list_runs(store_dir):
    """Tolerant store reader -> (rows, notes). Never raises on a weird store.

    Absence is a friendly line, not an error; rogue files and undecodable envelopes are
    skipped WITH a note, so a partial listing is never silently presented as complete.
    """
    store_dir = Path(store_dir)
    rows, notes = [], []
    if not store_dir.exists():
        return [], [f"no benchruns store at {store_dir} — run a plan first"]
    if not store_dir.is_dir():
        return [], [f"benchruns store path is not a directory: {store_dir}"]

    for entry in sorted(store_dir.iterdir()):
        if not entry.is_dir():
            notes.append(f"rogue entry skipped (not a run directory): {entry.name}")
            continue
        meta_path = entry / "meta.json"
        if not meta_path.exists():
            notes.append(f"run directory without meta.json skipped: {entry.name}")
            continue
        try:
            meta = json.loads(meta_path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
            notes.append(f"undecodable meta.json skipped: {entry.name} ({e})")
            continue
        if not isinstance(meta, dict):
            notes.append(f"meta.json is not a JSON object, skipped: {entry.name}")
            continue
        row = dict(meta)
        row["path"] = str(entry)
        row.setdefault("run_id", entry.name)

        # T9: `list` renders repo/mode/candidates/spend/verdict-presence/below-floor per run.
        # `results.json` may not exist yet (a run dir that only ever got as far as `meta.json`
        # -- a refused `run`, or a plan-only dir some other tool made) -- that is a NORMAL
        # state, not a rogue one, so it degrades to `None`/`[]` quietly rather than earning a
        # note the way a broken `meta.json` does above.
        row["repo"] = None
        row["mode"] = None
        row["candidates"] = []
        row["spend"] = None
        row["verdict_present"] = False
        row["below_floor"] = None
        results_path = entry / "results.json"
        if results_path.exists():
            try:
                results = json.loads(results_path.read_text())
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                results = None
            if isinstance(results, dict):
                row["repo"] = results.get("repo")
                row["mode"] = results.get("mode")
                row["candidates"] = list(results.get("candidates") or [])
                row["spend"] = results.get("spend")
                verdict = results.get("verdict")
                row["verdict_present"] = bool(verdict)
                row["below_floor"] = verdict.get("below_floor") if isinstance(verdict, dict) else None

        rows.append(row)

    if not rows and not notes:
        notes.append(f"benchruns store at {store_dir} is empty — run a plan first")
    return rows, notes


# ---------------------------------------------------------------------------------------------
# Issue-replay miner (PLAN D4, mode A): fix-commit pairs mined OFFLINE from the target's own
# `git log`, entirely through `git_target` -- never a second history read later. THE LEAK RULE
# lives here too: `build_prompt` composes only leak-free fields, never `reference_patch` or
# `test_blobs`.

#: Path-substring patterns (PLAN D4 default). A diff path matches when any pattern is a
#: substring of it (or a leading dir) -- deliberately loose, never a glob engine.
DEFAULT_TEST_PATTERNS = ("tests/", "test/", "spec/", "test_", "_test.", ".spec.")

#: `fixes #7` / `closes #7` / `resolved #7` etc, case-insensitive. Group 3 is the issue number.
ISSUE_REF_RE = re.compile(r"(fix(e[sd])?|close[sd]?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE)

#: GitHub squash-merge subjects: "... (#42)" at the end of the subject line.
SQUASH_MERGE_RE = re.compile(r"\(#(\d+)\)\s*$")

#: changed-LOC -> size_profile thresholds (PLAN D4/T2, structural, sanctioned). Anything
#: above the last threshold falls to "L". Labels are `data/pricing.json` `task_profiles`
#: keys -- data-driven, checked against the loaded pricing dict below, never hardcoded prices.
SIZE_THRESHOLDS = ((10, "XS"), (60, "S"), (250, "M"))

_LOG_FIELD_SEP = "\x1f"
_LOG_RECORD_SEP = "\x1e"
_ISSUE_LOG_FORMAT = f"%H{_LOG_FIELD_SEP}%s{_LOG_FIELD_SEP}%b{_LOG_RECORD_SEP}"

PROMPT_INSTRUCTIONS = (
    "Instructions:\n"
    "- Work only inside the current directory; you have no access to anything outside it.\n"
    "- Make the change needed to address the statement above.\n"
    "- Do not run anything that needs network access.\n"
    "- Do not ask clarifying questions -- make your best judgment call and proceed.\n"
)


def _matches_test_pattern(path, patterns):
    return any(pat in path for pat in patterns)


def _extract_issue_number(subject, body):
    """Issue number referenced by a commit message, or None. `ISSUE_REF_RE` (searched over
    the whole subject+body) wins; a squash-merge `(#N)` subject suffix is the fallback."""
    message = f"{subject}\n{body}"
    m = ISSUE_REF_RE.search(message)
    if m:
        return int(m.group(3))
    m = SQUASH_MERGE_RE.search(subject.strip())
    if m:
        return int(m.group(1))
    return None


def _changed_loc(patch_text):
    """Changed-line count of a unified diff: `+`/`-` content lines, excluding the
    `+++`/`---` file headers."""
    n = 0
    for line in patch_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+") or line.startswith("-"):
            n += 1
    return n


def _size_profile(changed_loc):
    for threshold, label in SIZE_THRESHOLDS:
        if changed_loc <= threshold:
            return label
    return "L"


def _pricing_task_profile_keys():
    """The `task_profiles` keys of `data/pricing.json` -- the single numeric source of
    truth. Reading key NAMES (not prices) to validate `size_profile` labels against.

    Loaded through `cost_report.load_pricing()` (which owns `PRICING_PATH`): this module
    neither re-derives that path nor parses that file itself.
    """
    data = _cr().load_pricing()
    return set((data.get("task_profiles") or {}).keys())


def _require_size_profile_labels():
    """Every `SIZE_THRESHOLDS` label must be a real `task_profiles` key. Checked ONCE per
    mining pass, by BOTH miners -- both emit `size_profile`, so both validate it."""
    profile_keys = _pricing_task_profile_keys()
    expected_labels = {label for _, label in SIZE_THRESHOLDS} | {"L"}
    missing = expected_labels - profile_keys
    if missing:
        raise ValueError(
            f"repo_bench size_profile labels missing from data/pricing.json task_profiles: "
            f"{sorted(missing)} (task_profiles keys are the single source of truth for "
            f"these labels -- fix the mismatch, never hardcode around it)"
        )


def _finalize_task(task):
    """Schema gate every mined record passes through -- the structural half of parity.

    Both miners emit exactly `TASK_RECORD_KEYS` and a `statement_source` drawn from
    `STATEMENT_SOURCES`. A drifting miner fails HERE, at mining time (free, offline),
    rather than as a `KeyError` in a consumer after dispatches have already been paid for.
    """
    keys = set(task)
    if keys != set(TASK_RECORD_KEYS):
        raise ValueError(
            f"repo_bench task record breaks the pinned schema for {task.get('task_id')!r}: "
            f"missing={sorted(set(TASK_RECORD_KEYS) - keys)} "
            f"extra={sorted(keys - set(TASK_RECORD_KEYS))} "
            f"(both miners emit identical key sets -- see TASK_RECORD_KEYS)"
        )
    if task["statement_source"] not in STATEMENT_SOURCES:
        raise ValueError(
            f"repo_bench task {task.get('task_id')!r} carries statement_source "
            f"{task['statement_source']!r}, not one of {', '.join(STATEMENT_SOURCES)} "
            f"(see STATEMENT_SOURCES -- a new source is added there, never ad hoc)"
        )
    return task


def _git_target_text(target_repo, *args, git_runner=None):
    """`git_target`, but a payload that is not UTF-8 text is REPORTED, not raised.

    `default_git_runner` decodes strictly (`text=True`), so a single latin-1 file in the
    target would otherwise abort a whole mining pass with an opaque `UnicodeDecodeError`
    (a `ValueError` subclass, which `main()` swallows into exit 2). The callers here degrade
    instead: skip that file/pair with a note. We deliberately do NOT set `errors="replace"`
    in `default_git_runner` -- that would silently corrupt the test blobs later written into
    grade copies.

    Returns (rc, output, undecodable); on `undecodable` the first two are (None, "").
    """
    try:
        rc, out = git_target(target_repo, *args, git_runner=git_runner)
    except UnicodeDecodeError:
        return None, "", True
    return rc, out, False


def default_gh_runner(argv):
    """Real subprocess runner for `gh` -> (rc, stdout+stderr). Free (no model spend), but it
    DOES hit the network and the user's `gh` auth -- constructed ONLY on the `--with-gh` CLI
    path (`cmd_plan`/`cmd_run`), NEVER as a parameter default anywhere: `mine_issue_tasks` and
    `build_plan` keep `gh_runner=None` exactly as before this flag existed, so no import or
    unset invocation can reach a real `gh` (T14; PLAN D4 -- "OPTIONAL, behind a flag, through
    an injectable runner, and never invoked by any test").
    """
    try:
        proc = subprocess.run(argv, capture_output=True, text=True)
    except FileNotFoundError:
        return 127, "gh: command not found -- is the GitHub CLI installed and on PATH?"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _classify_gh_failure(gh_rc, gh_out):
    """Best-effort classification of a failed `gh api` call into the concrete failure modes
    T14 names (PATH, auth, not found/private/rate-limited) -- matched against `gh`'s own error
    text, never invented. Falls back to a generic rc-only note when nothing matches; the
    caller always appends "-- fell back to commit message" so the degradation is never silent.

    T16: PR detection is NOT one of these branches. It is not a failure at all -- `gh api
    repos/<owner>/<name>/issues/<N>` returns rc=0 for a PR number (it is the SAME endpoint
    GitHub uses for both issues and pull requests); the caller discriminates by inspecting the
    parsed JSON payload for a `pull_request` key, after this function would already have been
    bypassed by the rc==0 success path. The old "is a pr" text match here dated from
    `gh issue view`, which this task retired precisely because it could not tell the two apart.
    """
    text = (gh_out or "").lower()
    if gh_rc == 127 or "command not found" in text or "no such file or directory" in text:
        return "gh not found on PATH"
    if "auth" in text and ("login" in text or "not logged" in text or "credential" in text):
        return "gh not authenticated (run `gh auth login`)"
    if "rate limit" in text:
        return "gh api rate-limited"
    if "could not resolve" in text or "not found" in text or "404" in text:
        return "issue not found (deleted or private)"
    return f"gh api failed (rc={gh_rc})"


# T15: `gh issue view <N>` with no `--repo` resolves the repository from the CURRENT WORKING
# DIRECTORY, not from `--repo`/`target_repo` -- the normal case is cwd = this plugin repo and
# target elsewhere, so every lookup silently queries the wrong project and fails, producing a
# confident-looking `gh enrichment: 0/N` that reads as a finding about the TARGET when it
# measured nothing. `--gh-repo OWNER/NAME` is required whenever `--with-gh` is set (a refusal,
# not a degradation -- a silent wrong-repo lookup is indistinguishable from a real result) and
# is never inferred from the target's `origin` remote: `remote`/`config` are not in
# `READ_ONLY_GIT` (GUARDRAILS forbids widening that allowlist), and inference would be wrong
# for a fork, whose issues live upstream, not at the fork's own remote.
_GH_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

#: T16: the exact substring `mine_issue_tasks` writes into a task's `notes` when `gh api`
#: reports the number is a pull request rather than an issue. `build_plan`'s enrichment label
#: greps for this ONE constant to count PRs out of the failures -- a single source of truth so
#: the note text and the count can never drift apart.
_GH_PR_NOTE_MARKER = "is a pull request, not an issue"


def validate_gh_repo(value):
    """`--gh-repo` must be exactly `OWNER/NAME` -- no scheme, no host, no trailing path
    segment. Raises `ValueError` naming the bad value; never strips a prefix or coerces a URL
    into shape (T15) -- an unvalidated string must never reach a `gh` argv."""
    if not _GH_REPO_RE.match(value or ""):
        raise ValueError(
            f"--gh-repo must look like OWNER/NAME (no scheme, no host, no trailing path "
            f"segment), got {value!r}"
        )
    return value


def _resolve_gh_repo(args):
    """Shared `plan`/`run` gate (T15): `--with-gh` without `--gh-repo` REFUSES rather than
    silently querying whatever repo the cwd happens to resolve to -- see the module note
    above `_GH_REPO_RE`. `--gh-repo` without `--with-gh` is accepted and simply unused (no
    lookup happens either way). Returns `(use_gh, gh_repo)`; raises `ValueError` (caught by
    `main()` -> stderr + exit 2, or by the caller for a run-dir-aware message) naming the
    problem in a plain sentence.
    """
    use_gh = bool(getattr(args, "with_gh", False))
    gh_repo = getattr(args, "gh_repo", None)
    if use_gh and not gh_repo:
        raise ValueError(
            "--with-gh requires --gh-repo OWNER/NAME -- gh resolves the repository from the "
            "current working directory, not from --repo, so an unset --gh-repo would silently "
            "query the wrong project"
        )
    if gh_repo is not None:
        validate_gh_repo(gh_repo)
    return use_gh, gh_repo


def mine_issue_tasks(
    target_repo, limit=8, test_patterns=DEFAULT_TEST_PATTERNS,
    git_runner=None, gh_runner=None, use_gh=False, exclude_subject=(), gh_repo=None,
):
    """Mine `target_repo`'s own history for fix-commit -> issue pairs (PLAN D4, mode A).

    OFFLINE by default and always through `git_target` (the read-only choke point) -- never
    a second history read later, which is why test blobs are extracted HERE. `gh_runner` is
    only ever invoked when the caller passes BOTH `use_gh=True` AND a runner; the CLI is the
    only place that wires a real one, and no test here takes that path.

    `gh_repo` (T15): `OWNER/NAME`, spliced into the `gh api repos/<gh_repo>/issues/<N>` path
    (T16) when set. WITHOUT it, the path uses the `{owner}/{repo}` placeholder, which `gh`
    resolves from the current working directory rather than `target_repo` -- the CLI
    (`_resolve_gh_repo`) refuses `use_gh=True` with no `gh_repo` before mining ever starts;
    this function itself stays permissive (an unset `gh_repo` here just uses the placeholder)
    so library-level callers and tests are unaffected.

    T16: `gh api repos/<owner>/<name>/issues/<N>` (NOT `gh issue view`) is the discriminator,
    because GitHub shares one number namespace between issues and pull requests and
    `gh issue view` cannot tell them apart -- it resolves a PR number happily and returns the
    PR body, which describes the fix rather than the bug (the leakiest text available). The
    `gh api` JSON payload carries a `pull_request` key if and only if the number is a PR; a
    hit on that key falls back to the commit-message statement and is never counted as
    enrichment, regardless of `gh`'s response code.

    `exclude_subject` (T13): an iterable of regex strings, compiled case-INsensitively and
    matched with `re.search` against the commit SUBJECT (first line) only. Default empty --
    absent means today's behavior, exactly: this is opt-in, never a built-in default pattern
    (silently dropping commits the user did not ask to drop is the failure class this kit
    spent four reviews closing). A commit matching any pattern is dropped from the mined
    task set and a note names it, so an excluded task set never reads as "this repo has
    little history" when it actually means "we filtered it". T19/F8: notes stop once `tasks`
    has already reached `limit` -- the exclusion CHECK stays first (unreordered), but exclusions
    walked over only to reach the end of the log after the quota was met are not counted, so
    the reported number reflects what mining the planned tasks actually required.

    Returns (tasks, notes) -- `notes` covers repo-level things (e.g. a root-commit skip, an
    excluded commit); each task also carries its own `notes` for task-scoped degradations
    (e.g. an unparseable `gh` response falling back to the commit message).
    """
    target_repo = Path(target_repo)
    tasks, notes = [], []

    exclude_res = []
    for pat in exclude_subject:
        try:
            exclude_res.append(re.compile(pat, re.IGNORECASE))
        except re.error as e:
            raise ValueError(f"--exclude-subject pattern {pat!r} is not a valid regex: {e}")

    _require_size_profile_labels()

    rc, log_out = git_target(
        target_repo, "log", "--no-merges", f"--format={_ISSUE_LOG_FORMAT}", git_runner=git_runner
    )
    _require_ok(rc, log_out, f"git log in {target_repo}")

    # T19/F8: `quota_met` tracks whether `tasks` has already reached `limit`. The exclusion
    # check below stays FIRST (T17R declined to reorder it, and this task does not either --
    # T13's tests and the count's meaning both depend on that order), so a commit walked AFTER
    # the quota is already satisfied still reaches this branch before the `len(tasks) >= limit`
    # break fires on the next non-excluded commit. Without `quota_met`, every excluded commit in
    # that trailing stretch is counted and reported, even though none of them was needed to
    # build the task set the run actually mined -- `--limit 1` against a bump-heavy history
    # reported "3 commit(s) excluded" for a run that only had to examine one. Once the quota is
    # met, further exclusions are real (the walk still passes over them) but not REPORTED: the
    # count stays honest about what mining the planned tasks actually required.
    quota_met = False
    for record in log_out.split(_LOG_RECORD_SEP):
        record = record.strip("\n")
        if not record.strip():
            continue
        parts = record.split(_LOG_FIELD_SEP)
        sha = parts[0].strip() if parts else ""
        subject = parts[1] if len(parts) > 1 else ""
        body = parts[2] if len(parts) > 2 else ""
        if not sha:
            continue

        issue = _extract_issue_number(subject, body)
        if issue is None:
            continue

        excluded_by = next(
            (pat for pat, rx in zip(exclude_subject, exclude_res) if rx.search(subject)), None
        )
        if excluded_by is not None:
            if not quota_met:
                notes.append(
                    f"commit {sha[:7]} excluded by --exclude-subject {excluded_by!r}: "
                    f"{subject.strip()}"
                )
            continue

        if len(tasks) >= limit:
            break

        rc, parent_out = git_target(target_repo, "rev-parse", f"{sha}^", git_runner=git_runner)
        if rc != 0:
            notes.append(
                f"root commit {sha[:7]} ({subject.strip()!r}) skipped -- no parent to diff against"
            )
            continue
        base = parent_out.strip()
        task_notes = []

        # Paths first (always ASCII-safe), so a non-UTF-8 payload in the diff itself can
        # still be reported against the files that caused it.
        rc, names_out = git_target(
            target_repo, "diff", "--no-color", "--no-ext-diff", "--name-only", base, sha,
            git_runner=git_runner,
        )
        _require_ok(rc, names_out, f"git diff --name-only {base}..{sha} in {target_repo}")
        touched_paths = [p for p in names_out.splitlines() if p.strip()]
        test_paths = [p for p in touched_paths if _matches_test_pattern(p, test_patterns)]

        # F4a (Phase 3 review): `--no-color --no-ext-diff`, exactly as `capture_patch` pins
        # them on the CANDIDATE side. A target repo carrying `color.ui = always` in its own
        # git config colours this diff, and ANSI escapes make every `+++`/`---` header
        # unparseable -- `_split_diff_by_file` then finds no blocks, `_strip_test_hunks`
        # returns "", `size_profile` collapses to XS for every task in that repo, and the
        # judge's `Patch A` renders EMPTY (100% deanonymisation). An external diff driver
        # (`diff.external`) would replace the format outright. Neither is exotic; both are
        # somebody's normal config.
        rc, patch, undecodable = _git_target_text(
            target_repo, "diff", "--no-color", "--no-ext-diff", base, sha, git_runner=git_runner
        )
        if undecodable:
            notes.append(
                f"fix commit {sha[:7]} skipped -- its diff is not UTF-8 decodable "
                f"(touched: {', '.join(touched_paths) or 'unknown'})"
            )
            continue
        _require_ok(rc, patch, f"git diff {base}..{sha} in {target_repo}")

        # Test blobs are extracted NOW -- a history-free sandbox cannot fetch them later.
        # A blob we cannot read is skipped WITH a note (a fix commit that DELETES a test
        # file, or a file that is not UTF-8 text); it never aborts the whole pass and
        # never silently pretends the oracle is available.
        test_blobs = {}
        for path in test_paths:
            rc, blob, undecodable = _git_target_text(
                target_repo, "show", f"{sha}:{path}", git_runner=git_runner
            )
            if undecodable:
                skip = (
                    f"test blob skipped (not UTF-8 decodable): {path} at {sha[:7]} -- "
                    f"it cannot serve as a tests-oracle blob"
                )
                notes.append(skip)
                task_notes.append(skip)
                continue
            if rc != 0:
                skip = (
                    f"test blob skipped (absent at the fix commit -- deleted by it?): "
                    f"{path} at {sha[:7]}"
                )
                notes.append(skip)
                task_notes.append(skip)
                continue
            test_blobs[path] = blob

        statement = None
        statement_source = None
        labels = []
        if use_gh and gh_runner is not None:
            # T16: `gh issue view <N>` cannot tell an issue number from a pull-request
            # number -- GitHub shares ONE namespace between them, so `gh issue view` resolves
            # a PR happily and returns its body, which is the LEAKIEST text available (a PR
            # description explains the fix, not the bug). `gh api
            # repos/<owner>/<name>/issues/<N>` hits the same underlying object as raw JSON,
            # and that JSON carries a `pull_request` key if and only if the number is a PR --
            # documented GitHub REST behavior (GET /repos/{owner}/{repo}/issues/{n} "returns
            # details for both issues and pull requests... if pull_request is present in the
            # payload it means the issue is a pull request"). `{owner}`/`{repo}` placeholders
            # (verified via `gh api --help`) resolve from the current working directory
            # exactly like `gh issue view` did, so the unset-`gh_repo` library path (T15)
            # keeps its prior cwd-resolution behavior unchanged.
            repo_path = gh_repo if gh_repo else "{owner}/{repo}"
            gh_argv = ["gh", "api", f"repos/{repo_path}/issues/{issue}"]
            try:
                gh_rc, gh_out = gh_runner(gh_argv)
            except Exception as e:  # pragma: no cover - defensive; no test takes this path
                gh_rc, gh_out = 1, str(e)
            if gh_rc == 0:
                try:
                    payload = json.loads(gh_out)
                    if "pull_request" in payload:
                        # THE DEFECT THIS TASK CLOSES: a PR body must never become the
                        # statement -- it explains the CURE, which is the leak. Do not use
                        # the PR title either; it is usually the same as the commit subject
                        # the commit-message fallback below already supplies.
                        task_notes.append(
                            f"#{issue} {_GH_PR_NOTE_MARKER} -- PR descriptions explain the "
                            f"fix, so its body was not used -- fell back to commit message"
                        )
                    else:
                        title = (payload.get("title") or "").strip()
                        body_text = (payload.get("body") or "").strip()
                        statement = (
                            title + ("\n\n" + body_text if body_text else "")
                        ).strip()
                        statement_source = "issue"
                except (json.JSONDecodeError, AttributeError, TypeError):
                    task_notes.append(
                        "gh api output unparseable -- fell back to commit message"
                    )
            else:
                detail = _classify_gh_failure(gh_rc, gh_out)
                task_notes.append(f"{detail} -- fell back to commit message")

        if statement is None:
            statement = (subject.strip() + ("\n\n" + body.strip() if body.strip() else "")).strip()
            statement_source = "commit-message"
            labels.append("statement from commit message (weaker than issue text)")

        task = {
            "task_id": f"issue-{issue}-{sha[:7]}",
            "mode": "issue-replay",
            "issue": issue,
            "base_commit": base,
            "fix_commit": sha,
            "subject": subject.strip(),
            "statement": statement,
            "statement_source": statement_source,
            "reference_patch": patch,
            # None on purpose: an issue-replay sandbox is built off `base_commit`, which is
            # ALREADY the buggy state -- nothing to inject. See SETUP-PATCH LAW above.
            "setup_patch": None,
            "test_blobs": test_blobs,
            # Keyed on the blobs we actually HOLD, not the paths we merely saw: a blob that
            # was skipped above cannot grade anything, and claiming otherwise would inflate
            # objective coverage (PLAN D5).
            "oracle_tests_available": bool(test_blobs),
            # P1-F5 + Nit (carried into T6): `patch` is the FULL fix diff, test hunks
            # included -- sized on the STRIPPED patch (grading/sizing boundary, never the
            # mining boundary: `reference_patch` above stays the full, unstripped diff,
            # exactly as T2 mined it) so a candidate is never priced for LOC it structurally
            # cannot produce (the withheld test blobs never reach its sandbox).
            "size_profile": _size_profile(_changed_loc(_strip_test_hunks(patch, test_patterns))),
            "labels": labels,
            "notes": task_notes,
        }
        tasks.append(_finalize_task(task))
        if len(tasks) >= limit:
            quota_met = True

    return tasks, notes


def build_prompt(task):
    """The candidate-facing prompt -- composed ONLY from leak-free fields.

    THE LEAK RULE (PLAN D4/R2): `reference_patch` and `test_blobs` must never reach a
    candidate's prompt or sandbox. This function structurally cannot leak them -- it reads
    only `statement` (falling back to `subject`) plus static instructions; it never touches
    `reference_patch`, `test_blobs`, or any touched-path field.
    """
    statement = (task.get("statement") or task.get("subject") or "").strip()
    return f"{statement}\n\n{PROMPT_INSTRUCTIONS}"


# ---------------------------------------------------------------------------------------------
# General-mode miner (PLAN D4, mode B) -- the fallback when issue-replay yields no usable
# pairs: inject one deterministic textual mutation, prove RED (the target's own `test_cmd`
# fails in a scratch sandbox, at zero model cost), and hand the candidate the reverse-mutation
# diff as the reference patch. An objective oracle by construction -- no green mutation is
# ever admitted.

#: Ordered `(name, pattern, replacement)` textual operators. Order IS the tie-break: within a
#: single candidate line, only the FIRST operator whose `pattern` appears is applied -- "first
#: match wins per candidate site" (PLAN D4/T3). One mutation per admitted task.
MUTATION_OPERATORS = (
    ("eq-to-neq", "==", "!="),
    ("le-to-lt", "<=", "<"),
    ("ge-to-gt", ">=", ">"),
    ("plus-one-to-minus-one", "+ 1", "- 1"),
    ("true-to-false", "True", "False"),
    ("lower-true-to-false", "true", "false"),
    ("and-to-or", " and ", " or "),
    ("amp-amp-to-pipe-pipe", "&&", "||"),
)

#: Suffixes skipped when enumerating mutation candidates -- binary/asset files a textual
#: operator can never sensibly touch.
BINARY_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".tar", ".gz", ".tgz",
    ".woff", ".woff2", ".ttf", ".eot", ".exe", ".dll", ".dylib", ".so", ".bin",
    ".pyc", ".pyo", ".jar", ".class", ".o", ".a", ".wasm",
)

#: Fixed statement handed to the candidate for every general-mode task. Deliberately generic
#: -- it names neither the mutated file nor the operator (THE LEAK RULE extends here: the
#: bug's location is part of the "solution").
GENERAL_STATEMENT = (
    "The test suite fails on this repository as it currently stands. Find the bug, "
    "then fix it so the test suite passes again."
)

#: The `subject` a general-mode record carries. Issue-replay's subject is the fix commit's
#: subject line; a synthetic task has no such thing, but the field is part of the pinned
#: schema (T7's judge prompt reads it, `build_prompt` falls back to it), so it must exist
#: AND be leak-free -- naming neither the mutated file nor the operator, exactly like
#: GENERAL_STATEMENT. Both are covered by the same statement-leak test.
GENERAL_SUBJECT = "Failing test suite: locate the defect, then repair it"

SANDBOX_MUTATED_MESSAGE = "repo-bench sandbox mutated (red-validated)"


def default_test_runner(cmd, cwd):
    """Local test-command runner -> (rc, output). Free, offline, no model, no network.

    `cmd` may be a shell string (run through the shell, matching what a user hands
    `--test-cmd`) or an argv list (run directly, no shell).

    What is TRUE of this function (F9 -- the previous docstring claimed it "is never exercised
    by a test here", and it was, via a test that drove `main()` with no injected runner and so
    shell-resolved a bare command name off PATH): it only ever runs with `cwd` set to a
    sandbox or scratch copy we built, never a target repo, never this repo, and only when the
    user explicitly supplied `--test-cmd` (PLAN D11). Tests DO exercise it, deliberately -- a
    stub runner executes nothing, so it can never catch what a real test command does to a
    sandbox -- but only ever with a local, offline, harmless command they construct themselves
    (a `sys.executable` invocation), never a PATH-resolved name and never a real test suite.
    """
    if isinstance(cmd, (list, tuple)):
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    else:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, shell=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _first_matching_operator(line):
    """The first `MUTATION_OPERATORS` entry whose pattern appears in `line`, or None."""
    for op in MUTATION_OPERATORS:
        _name, pattern, _replacement = op
        if pattern in line:
            return op
    return None


def mine_general_tasks(
    target_repo, commit, limit=8, test_cmd=None, test_runner=None,
    scratch_dir=None, git_runner=None,
):
    """Mine synthetic mutation-repair tasks (PLAN D4, mode B).

    Requires `test_cmd` -- there is no mutation-repair fallback without one (D4); raises
    `ValueError` otherwise. Enumerates source files from `commit` (skipping
    `DEFAULT_TEST_PATTERNS` and `BINARY_SUFFIXES`), scans their content for operator sites,
    and for each candidate mutation builds its OWN scratch sandbox via `make_sandbox` off the
    same `commit` (no target history, exactly like issue-replay's sandboxes), applies the
    single-line mutation, and runs `test_cmd` through `test_runner` (injectable
    `(cmd, cwd) -> (rc, output)`; default `default_test_runner`). The task is ADMITTED only
    when the mutation is RED (rc != 0); a green mutation is discarded with a note -- it is
    not a discriminating bug.

    The scan is bounded: it stops after EXAMINING `limit * 4` candidate sites (not files),
    win or lose, and also stops once `limit` tasks are admitted -- whichever comes first.
    """
    if not test_cmd:
        raise ValueError(
            "repo_bench general mode needs a test command (PLAN D4) -- pass --test-cmd; "
            "there is no mutation-repair fallback without one"
        )

    target_repo = Path(target_repo)
    runner = test_runner or default_test_runner
    tasks, notes = [], []

    _require_size_profile_labels()

    rc, names_out = git_target(
        target_repo, "ls-tree", "-r", "--name-only", commit, git_runner=git_runner
    )
    _require_ok(rc, names_out, f"git ls-tree in {target_repo}")
    candidate_paths = [
        p for p in names_out.splitlines()
        if p.strip()
        and not _matches_test_pattern(p, DEFAULT_TEST_PATTERNS)
        and not p.lower().endswith(BINARY_SUFFIXES)
    ]

    #: F8 (Phase 1 review, carried into T4): filled in by `_scan` below so the caller can
    #: tell "the bound truncated the scan" apart from "the repo simply ran out of sites" --
    #: a mutable single-element container rather than `nonlocal` so it survives past `_scan`.
    examined_total = [0]

    def _scan(base_scratch):
        examined = 0
        site_n = 0
        base_scratch = Path(base_scratch)
        for path in candidate_paths:
            if len(tasks) >= limit or examined >= limit * 4:
                break
            rc, content, undecodable = _git_target_text(
                target_repo, "show", f"{commit}:{path}", git_runner=git_runner
            )
            if undecodable:
                # One latin-1 file must not abort the pass; textual mutation operators
                # could not have applied to it anyway.
                notes.append(
                    f"file skipped (not UTF-8 decodable): {path} -- no textual mutation "
                    f"site can be read from it"
                )
                continue
            if rc != 0:
                continue
            orig_lines = content.splitlines(keepends=True)
            for line_idx, line in enumerate(orig_lines):
                if len(tasks) >= limit or examined >= limit * 4:
                    break
                op = _first_matching_operator(line)
                if op is None:
                    continue
                examined += 1
                op_name, pattern, replacement = op
                site_n += 1

                site_dir = base_scratch / f"site-{site_n}"
                info = make_sandbox(target_repo, commit, site_dir, git_runner=git_runner)
                sandbox_path = Path(info["path"])
                file_path = sandbox_path / path

                try:
                    mutated_lines = list(orig_lines)
                    mutated_lines[line_idx] = mutated_lines[line_idx].replace(
                        pattern, replacement, 1
                    )
                    mutated_text = "".join(mutated_lines)
                    file_path.write_text(mutated_text)

                    rc_test, _output = runner(test_cmd, str(sandbox_path))
                    if rc_test == 0:
                        notes.append(
                            f"mutation discarded (green, not a discriminating bug): "
                            f"site {site_n} ({op_name}) -- the mutated tests still pass"
                        )
                        continue

                    # RED -- admit. Commit the mutated state, then diff it AGAINST the
                    # sandbox's (unmutated) init commit: mutated_commit -> init_commit is
                    # exactly the reverse-mutation diff -- applying it to the mutated file
                    # yields the original.
                    #
                    # F2 (Phase 2 review): stage and diff THE MUTATED FILE ONLY. Red-validation
                    # runs the target's REAL test command in this sandbox, and a real suite
                    # leaves artifacts behind (`__pycache__/*.pyc`, coverage data, build
                    # output). A `git add -A` here swept those into the mutated commit, so both
                    # patches picked up binary hunks with no full index line -- `git apply`
                    # then failed on the candidate's sandbox and took the whole run out with
                    # it, and the artifacts inflated `_changed_loc` -> `size_profile` -> the
                    # priced estimate on the way past. The mutation is one known line in one
                    # known file; nothing else may enter either patch. Every general-mode test
                    # that injects a stub test runner is blind to this by construction -- the
                    # stub executes nothing, so it creates nothing.
                    rc_c, out_c = git_sandbox(
                        sandbox_path, "add", "--", path, git_runner=git_runner
                    )
                    _require_ok(rc_c, out_c, f"git add in mutation sandbox {sandbox_path}")
                    rc_c, out_c = git_sandbox(
                        sandbox_path, "commit", "-q", "-m", SANDBOX_MUTATED_MESSAGE,
                        git_runner=git_runner,
                    )
                    _require_ok(rc_c, out_c, f"git commit in mutation sandbox {sandbox_path}")
                    rc_c, mutated_commit = git_sandbox(
                        sandbox_path, "rev-parse", "HEAD", git_runner=git_runner
                    )
                    _require_ok(
                        rc_c, mutated_commit, f"git rev-parse in mutation sandbox {sandbox_path}"
                    )
                    mutated_commit = mutated_commit.strip()

                    rc_c, reference_patch = git_sandbox(
                        sandbox_path, "diff", "--no-color", "--no-ext-diff",
                        mutated_commit, info["init_commit"], "--", path, git_runner=git_runner,
                    )
                    _require_ok(
                        rc_c, reference_patch, f"git diff in mutation sandbox {sandbox_path}"
                    )

                    # The FORWARD diff -- init_commit -> mutated_commit -- is the bug itself.
                    # SETUP-PATCH LAW: a candidate's sandbox is built fresh off `commit`, which
                    # is UNMUTATED and therefore GREEN; the dispatch path MUST `git apply` this
                    # to it before dispatch or the candidate is handed a passing repo and told
                    # its tests fail. This scratch sandbox is thrown away; the patch is the only
                    # thing that survives it.
                    rc_c, setup_patch = git_sandbox(
                        sandbox_path, "diff", "--no-color", "--no-ext-diff",
                        info["init_commit"], mutated_commit, "--", path, git_runner=git_runner,
                    )
                    _require_ok(rc_c, setup_patch, f"git diff in mutation sandbox {sandbox_path}")

                    n = len(tasks) + 1
                    task = {
                        "task_id": f"mut-{n}-{Path(path).stem}",
                        "mode": "general",
                        # None on purpose (pinned schema): a synthetic task replays no issue and
                        # has no fix commit in the target's history. Absent keys would land as a
                        # KeyError in a consumer AFTER dispatches were paid for.
                        "issue": None,
                        "base_commit": str(commit),
                        "fix_commit": None,
                        "subject": GENERAL_SUBJECT,
                        "statement": GENERAL_STATEMENT,
                        "statement_source": "generated",
                        "reference_patch": reference_patch,
                        "setup_patch": setup_patch,
                        "test_blobs": {},
                        "oracle_tests_available": True,
                        "size_profile": _size_profile(_changed_loc(reference_patch)),
                        "labels": ["synthetic mutation-repair task"],
                        "notes": [],
                    }
                    tasks.append(_finalize_task(task))
                finally:
                    # F1 (Phase 2 review): the scratch sandbox dies with its red check. When
                    # `scratch_dir` is `<run-dir>/work` (which is what `run` passes, F11b),
                    # every one of these sits ONE `../` from a candidate's cwd, and its init
                    # commit -- plus its worktree, for a green discard -- is the UNMUTATED
                    # source: the answer, readable with `cat`. Nothing here is needed after
                    # the two patches have been extracted.
                    shutil.rmtree(site_dir, ignore_errors=True)

        examined_total[0] = examined

    if scratch_dir is not None:
        _scan(scratch_dir)
    else:
        with tempfile.TemporaryDirectory(prefix="repo-bench-mutate-") as tmp:
            _scan(tmp)

    # F8 (Phase 1 review): the scan is bounded (`limit * 4` sites examined); if it hit that
    # bound WITHOUT admitting `limit` tasks, coverage is partial -- the repo was not scanned
    # exhaustively, and a consumer (T4's plan card) must say so rather than reading the short
    # task list as "we looked at everything". Silent truncation is the failure mode (D8).
    if len(tasks) < limit and examined_total[0] >= limit * 4:
        notes.append(
            f"general mode: partial coverage -- the bounded scan stopped after examining "
            f"{examined_total[0]} candidate site(s) (limit * 4 = {limit * 4}) and admitted "
            f"only {len(tasks)}/{limit} task(s); the repo was not scanned exhaustively"
        )
    elif len(tasks) < limit:
        # F9 (Phase 4 review): asking for 3 and getting 1 said NOTHING unless the examine bound
        # had been hit, so a short task list read as "that is all there was" with no evidence
        # either way. This is the OTHER shortfall and a different fact: the repo WAS scanned
        # exhaustively and simply did not yield more red-validating mutation sites. Deliberately
        # not worded as "partial coverage" and deliberately not promoted to a plan LABEL --
        # coverage here is complete, the yield is just below what was asked for.
        notes.append(
            f"general mode: mined {len(tasks)}/{limit} requested task(s) -- the repo was "
            f"scanned exhaustively ({examined_total[0]} candidate site(s) examined) and no "
            f"further site produced a mutation the test command validated RED"
        )

    return tasks, notes


def choose_mode(issue_tasks, min_needed):
    """Auto mode pick (PLAN D4) -> (mode, reason). `reason` is always a printable sentence.

    issue-replay wins once it has cleared `min_needed` usable pairs (T8's evidence floor,
    `MIN_EVIDENCE_TASKS`); otherwise general (mutation-repair) is the honest fallback.
    """
    n = len(issue_tasks)
    if n >= min_needed:
        return "issue-replay", (
            f"issue-replay: mined {n} usable issue-fix pair(s), meeting the floor of "
            f"{min_needed} (PLAN D4/D7) -- no need for the mutation-repair fallback"
        )
    return "general", (
        f"general (mutation-repair): issue-replay mined only {n} usable pair(s), below the "
        f"floor of {min_needed} (PLAN D4) -- falling back to red-validated mutation tasks"
    )


# ---------------------------------------------------------------------------------------------
# `plan`: the priced matrix (PLAN D1/D6/D10), and `run`'s structural refusal (PLAN D1). Pricing
# reuse only -- `estimate_dispatch_usd` is the ONE place tokens x rate happens; every literal
# price and every model id lives in data/pricing.json, loaded through `cost_report`, never here.

#: The task-profile every judge grade is priced at (PLAN D1/T4) -- a judge grade is a short,
#: bounded read-and-score dispatch, not a full task-sized generation.
JUDGE_GRADE_PROFILE = "XS"

#: The estimate caveat every plan card carries (PLAN D1) -- a plan total is priced from
#: `task_profiles`, never from real usage, and must never be read as a bill.
ESTIMATE_CAVEAT_LABEL = "planned estimate from task_profiles — not a bill"


def _split_models(raw):
    """`--models a,b,c` -> `["a", "b", "c"]`, trimmed, empties dropped, order preserved."""
    return [m.strip() for m in (raw or "").split(",") if m.strip()]


def validate_ceiling(max_usd):
    """PLAN D1 / GUARDRAILS: `--max-usd` must be a finite, non-negative number before it is
    trusted for EITHER the structural "both flags present" gate or any spend comparison.
    `float("nan")` parses cleanly through argparse's `type=float` yet defeats every `x >
    ceiling` comparison by IEEE-754 (nan compares False against everything), and a negative
    ceiling is nonsensical as a spend cap. This is the ONE place that guard lives -- T5's
    per-dispatch re-check (spent-so-far + next estimate > ceiling) must call this same
    helper rather than re-deriving the check, so the guard can never drift between the two
    call sites. Raises `ValueError` naming the bad value; never coerces, clamps, or
    defaults -- a malformed ceiling is a refusal, not a fallback.
    """
    if max_usd is None:
        return None
    if not math.isfinite(max_usd) or max_usd < 0:
        raise ValueError(
            f"--max-usd must be a finite, non-negative number, got {max_usd!r}"
        )
    return max_usd


def estimate_dispatch_usd(model_id, profile_key, pricing):
    """One dispatch's estimated cost (PLAN D1/D10): `task_profiles[profile_key]` tokens x
    this model's per-token rate. Rates come from `cost_report.match_model` + `.rates_for`
    (current time -- a plan estimates what a dispatch would cost TODAY, not at some
    intro-pricing date that may since have lapsed); the only local arithmetic is
    tokens/1e6 x rate. No literal price, ratio, or model id anywhere in this function.
    """
    cr = _cr()
    key = cr.match_model(model_id, pricing)
    if key is None:
        raise KeyError(
            f"repo_bench cannot price model id {model_id!r}: cost_report.match_model found no "
            f"entry in data/pricing.json (valid ids: {', '.join(pricing['models'])})"
        )
    profile = pricing.get("task_profiles", {}).get(profile_key)
    if profile is None:
        raise KeyError(
            f"repo_bench cannot price task profile {profile_key!r}: not in data/pricing.json "
            f"task_profiles (valid: {', '.join(pricing.get('task_profiles', {}))})"
        )
    input_rate, output_rate = cr.rates_for(key, datetime.now(timezone.utc), pricing)
    return (
        profile["input_tokens"] * input_rate + profile["output_tokens"] * output_rate
    ) / 1e6


def _default_judge_id(pricing, candidate_ids):
    """PLAN D6: the default judge is the first model, in pricing-file order, of the HIGHEST
    populated tier that is NOT entirely made of candidates -- walking `ce.TIER_ORDER`
    downward (frontier -> haiku). None if every model in the roster is a candidate.
    """
    ce = _ce()
    models = pricing["models"]
    for tier in reversed(ce.TIER_ORDER):
        for mid, info in models.items():
            if info.get("tier") == tier and mid not in candidate_ids:
                return mid
    return None


#: T18: the live run recorded in `.claude/kits/repo-bench/NOTES.md` -- `task_profiles`
#: measured 8.7x-11.9x low against real agentic spend on a large TypeScript codebase, and a
#: plan total quoted with no calibration reads as a number nobody has ever checked. This
#: label fires only when the store holds NO usable actual/estimate pairs at all -- absence
#: must be as visible as presence (T18 do-3), never silently omitted.
CALIBRATION_NONE_LABEL = (
    "calibration: no prior-run actuals in the store yet -- task_profiles estimates are "
    "UNVALIDATED; size --max-usd against that, not against the raw total below"
)


def _calibration_rows(store_dir):
    """Every objectively-priced actual/estimate pair recorded across a benchruns store's
    completed runs -> a list of `{"run_id", "task_id", "model", "size_profile", "ratio"}`
    rows. Tolerant exactly like `list_runs`: a `None`/absent/non-directory store, an
    unreadable or malformed `results.json`, or a cell missing either dollar figure simply
    contributes nothing -- never a crash, never a guessed ratio (GUARDRAILS: never invent a
    ratio from zero data).

    Only `usd_basis: "actual"` cells count: an `estimated` cell compared against its own
    estimate is a ratio of 1 by construction, not a measurement of anything. `size_profile`
    is joined in from the RUN'S OWN records via `_task_size_profiles` (a results.json cell
    does not carry one) and is `None` when that join fails -- such a row still counts toward
    the OVERALL ratio (it is real recorded spend) but is dropped from the per-size breakdown,
    which must never attribute a ratio to a size it cannot prove (T18 do-2/note).
    """
    if store_dir is None:
        return []
    store_dir = Path(store_dir)
    if not store_dir.exists() or not store_dir.is_dir():
        return []

    rows = []
    for entry in sorted(store_dir.iterdir()):
        if not entry.is_dir():
            continue
        results_path = entry / "results.json"
        if not results_path.exists():
            continue
        try:
            results = json.loads(results_path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue
        if not isinstance(results, dict):
            continue
        cells = results.get("cells")
        if not cells:
            continue
        profiles, _notes = _task_size_profiles(entry)
        run_id = results.get("run_id", entry.name)
        for cell in cells:
            if not isinstance(cell, dict) or cell.get("skipped"):
                continue
            if cell.get("usd_basis") != "actual":
                continue
            actual, estimate = cell.get("usd"), cell.get("estimated_usd")
            if not isinstance(actual, (int, float)) or not isinstance(estimate, (int, float)):
                continue
            if estimate <= 0:
                continue
            rows.append({
                "run_id": run_id,
                "task_id": cell.get("task_id"),
                "model": cell.get("model"),
                "size_profile": profiles.get(cell.get("task_id")),
                "ratio": actual / estimate,
            })
    return rows


def _calibration_breakdown(rows, key):
    """`rows` grouped by `key` (`"size_profile"` or `"model"`) -> `{group: {"ratio", "n"}}`,
    each group's own median ratio and sample size. Rows whose group value is `None` are
    dropped, never folded into an "unknown" bucket (T18 do-2: a ratio must never be presented
    as applying somewhere it was not measured)."""
    groups = {}
    for row in rows:
        val = row.get(key)
        if val is None:
            continue
        groups.setdefault(val, []).append(row["ratio"])
    return {
        val: {"ratio": _median(ratios), "n": len(ratios)}
        for val, ratios in sorted(groups.items())
    }


def build_calibration(store_dir):
    """T18: how wrong `task_profiles` estimates have measured on THIS store's own completed
    live cells -- reported beside the plan total, never folded into it (GUARDRAILS: report,
    never silently adjust). `store_dir=None` or an absent/empty store both resolve to the
    same honest "no history" shape; a caller that never points this at a real store gets the
    same visible absence a caller with an empty one does, never a silent skip.

    Returns a JSON-serializable dict: `available`, `n_cells`, `n_runs`, `overall_ratio`
    (the MEDIAN, never a mean -- one outlier dispatch must not drag the whole line),
    `by_size`/`by_model` breakdowns (each entry its own median + sample size), and `labels`
    -- the lines the plan card prints, always at least one so absence is never silent.
    """
    rows = _calibration_rows(store_dir)
    if not rows:
        return {
            "available": False,
            "n_cells": 0,
            "n_runs": 0,
            "overall_ratio": None,
            "by_size": {},
            "by_model": {},
            "labels": [CALIBRATION_NONE_LABEL],
        }

    ratios = [r["ratio"] for r in rows]
    n_runs = len({r["run_id"] for r in rows})
    overall = _median(ratios)
    by_size = _calibration_breakdown(rows, "size_profile")
    by_model = _calibration_breakdown(rows, "model")

    labels = [
        f"calibration: past runs cost {overall:.1f}x their estimate (median over "
        f"{len(rows)} cell(s) in {n_runs} run(s)) -- NOT applied to the total below; size "
        f"--max-usd against this, not the raw estimate"
    ]
    if by_size:
        labels.append(
            "calibration by size: " + ", ".join(
                f"{size}={info['ratio']:.1f}x (n={info['n']})"
                for size, info in by_size.items()
            )
        )
    if by_model:
        labels.append(
            "calibration by model: " + ", ".join(
                f"{model}={info['ratio']:.1f}x (n={info['n']})"
                for model, info in by_model.items()
            )
        )
    return {
        "available": True,
        "n_cells": len(rows),
        "n_runs": n_runs,
        "overall_ratio": overall,
        "by_size": by_size,
        "by_model": by_model,
        "labels": labels,
    }


def build_plan(
    target_repo, models, mode="auto", limit=8, test_cmd=None, judge=None, pricing=None,
    commit=None, scratch_dir=None, git_runner=None, test_runner=None, gh_runner=None,
    use_gh=False, tasks_out=None, exclude_subject=(), gh_repo=None, setup_cmd=None,
    store_dir=None,
):
    """Price the whole models x tasks matrix (PLAN D1) -> a JSON-serializable plan card.

    Candidates are resolved (deduped, order-preserving) via `ce.resolve_model` -- an unknown
    id or tier propagates its own KeyError listing message, unchanged. The judge resolves per
    D6 (`_default_judge_id`) unless `judge` is given; a judge that is also a candidate is a
    hard refusal (`ValueError`). Mining always runs the issue-replay miner first (needed for
    `auto`'s decision AND for F9's oracle-available count in the mode reason); general mode
    additionally mines mutation-repair tasks through `scratch_dir` (F11b -- the caller is
    responsible for pointing this at `<run-dir>/work` when a run dir exists; PLAN D3/D11 say
    mutation only ever happens under it).

    `tasks_out`, when given a list, is extended with the FULL mined task records the card only
    summarises. `run` needs them (a prompt, a `setup_patch`, a reference patch) and must not
    re-mine to get them: general-mode mining is stochastic in the sense that matters -- a
    second pass builds new scratch sandboxes and could admit a different task set than the one
    the user was just quoted a price for. The card itself stays summary-only on purpose: it is
    what gets printed, and `reference_patch`/`test_blobs` are exactly what must never be shown.

    `store_dir` (T18), when given, is read ONLY to build the calibration line -- how wrong
    `task_profiles` estimates have measured against prior runs' own recorded actuals
    (`build_calibration`). It is never written here (`plan` never touches the store) and
    `None` degrades to the same honest "no calibration data" shape an absent/empty store
    does -- never a silent omission.
    """
    if pricing is None:
        pricing = _cr().load_pricing()
    ce = _ce()
    target_repo = Path(target_repo)

    candidate_ids = []
    seen = set()
    for m in models:
        resolved = ce.resolve_model(pricing, m)
        if resolved not in seen:
            seen.add(resolved)
            candidate_ids.append(resolved)

    if judge is not None:
        judge_id = ce.resolve_model(pricing, judge)
        if judge_id in candidate_ids:
            raise ValueError(
                f"repo_bench refuses judge {judge_id!r}: it is also a candidate in this run "
                f"(PLAN D6 -- a judge grading its own patches is a hard refusal); candidates: "
                f"{', '.join(candidate_ids)}"
            )
    else:
        judge_id = _default_judge_id(pricing, candidate_ids)
        if judge_id is None:
            raise ValueError(
                "repo_bench cannot resolve a default judge (PLAN D6): every model in "
                f"data/pricing.json is already a candidate ({', '.join(candidate_ids)}) -- "
                f"pass --judge explicitly"
            )

    if commit is not None:
        base_commit = str(commit)
    else:
        rc, out = git_target(target_repo, "rev-parse", "HEAD", git_runner=git_runner)
        _require_ok(rc, out, f"git rev-parse HEAD in {target_repo}")
        base_commit = out.strip()

    # T17R/F6: when the caller has already FORCED general mode, every mined issue task is
    # discarded a few lines below -- so enriching them would spend one real `gh` API call per
    # task that will never be run. Mining still happens (the general branch needs `base_commit`
    # and the notes), but with enrichment off. `auto` cannot do this: its decision is made FROM
    # the mined pairs, so they have to be mined first.
    mining_use_gh = use_gh and mode != "general"
    issue_tasks, issue_notes = mine_issue_tasks(
        target_repo, limit=limit, git_runner=git_runner, gh_runner=gh_runner,
        use_gh=mining_use_gh, exclude_subject=exclude_subject, gh_repo=gh_repo,
    )
    oracle_available = sum(1 for t in issue_tasks if t["oracle_tests_available"])
    mining_notes = list(issue_notes)
    excluded_count = sum(1 for n in issue_notes if "excluded by --exclude-subject" in n)

    # T14: only relevant on the `--with-gh` path -- when enrichment was never attempted
    # (use_gh False, or no issue-referencing commits mined) this must render nothing rather
    # than a misleading "0/0". The ratio is the number that says whether the leak mitigation
    # actually worked on this repo, and it must be visible on the card before spend.
    #
    # T16: the ratio must count ONLY genuine issues -- a PR body must never inflate it, since
    # that is precisely the mislabel this task exists to remove. `pr_count` separates PR
    # numbers out of the denominator's failures so a reader can see WHY enrichment fell short
    # (mostly PRs, vs. mostly gh failures) rather than one undifferentiated miss count.
    #
    # T17R/F6: computed here but only ATTACHED to the card when the resolved mode is
    # issue-replay (see below). It is a ratio about `issue_tasks`, and a general-mode run
    # replaces `tasks` with mutation-repair tasks — reporting an enrichment ratio about tasks
    # that are not in the run is a number describing something the user is not buying.
    enrichment_label = None
    if mining_use_gh and issue_tasks:
        enriched = sum(1 for t in issue_tasks if t.get("statement_source") == "issue")
        pr_count = sum(
            1 for t in issue_tasks
            if any(_GH_PR_NOTE_MARKER in n for n in t.get("notes", ()))
        )
        enrichment_label = (
            f"gh enrichment: {enriched}/{len(issue_tasks)} task(s) used real issue text"
        )
        if pr_count:
            enrichment_label += f" ({pr_count} were pull requests)"

    if mode == "auto":
        if test_cmd:
            resolved_mode, reason = choose_mode(issue_tasks, MIN_EVIDENCE_TASKS)
        else:
            # D4: general mode needs --test-cmd; without one the fallback does not exist, so
            # auto has no honest choice but issue-replay -- regardless of the D7 floor.
            resolved_mode = "issue-replay"
            reason = (
                f"issue-replay: no --test-cmd supplied, so the general (mutation-repair) "
                f"fallback is unavailable (PLAN D4) -- using the {len(issue_tasks)} mined "
                f"issue-fix pair(s) regardless of the {MIN_EVIDENCE_TASKS}-task evidence floor"
            )
    elif mode in ("issue-replay", "general"):
        resolved_mode, reason = mode, f"{mode}: forced by --mode"
    else:
        raise ValueError(f"unknown mode {mode!r}; valid: auto, issue-replay, general")

    if resolved_mode == "issue-replay":
        # F9 (Phase 1 review): `choose_mode` counts PAIRS, not objectively-scorable ones --
        # print the oracle-available count alongside the pair count so a below-floor outcome
        # (an issue-replay run with few/no scorable pairs, chosen over a general fallback
        # that would have cleared D7) is visible in the reason BEFORE the user spends.
        reason = (
            f"{reason} -- {oracle_available}/{len(issue_tasks)} mined issue-fix pair(s) are "
            f"objectively scorable (oracle_tests_available); PLAN D7 floor is "
            f"{MIN_EVIDENCE_TASKS}"
        )

    labels = [ESTIMATE_CAVEAT_LABEL]
    if excluded_count:
        # T13: same posture F8's "partial coverage" label already uses -- an exclusion
        # summary must be visible on the plan card itself, not buried only in `notes`.
        labels.append(f"{excluded_count} commit(s) excluded by --exclude-subject")
    if enrichment_label and resolved_mode == "issue-replay":
        labels.append(enrichment_label)

    if resolved_mode == "general":
        general_tasks, general_notes = mine_general_tasks(
            target_repo, base_commit, limit=limit, test_cmd=test_cmd, test_runner=test_runner,
            scratch_dir=scratch_dir, git_runner=git_runner,
        )
        tasks = general_tasks
        mining_notes.extend(general_notes)
        # F8: a partial-coverage note is data D8 says must ride as a LABEL, visible at the
        # top of the card -- not buried only in the notes list where it reads as decoration.
        for note in general_notes:
            if "partial coverage" in note:
                labels.append(note)
    else:
        tasks = issue_tasks

    # T17: `plan` never runs a setup command -- it never runs a test command either. Say which
    # of the two things a configured `--setup-cmd` will do, so "the plan printed nothing about
    # it" is never the way a user finds out.
    if setup_cmd:
        mining_notes.append(SETUP_WITHOUT_TEST_CMD_NOTE if not test_cmd else SETUP_PLAN_NOTE)

    if tasks_out is not None:
        tasks_out.extend(tasks)

    task_summaries = [
        {
            "task_id": t["task_id"],
            "size_profile": t["size_profile"],
            "oracle_tests_available": t["oracle_tests_available"],
        }
        for t in tasks
    ]

    judge_unit_cost = estimate_dispatch_usd(judge_id, JUDGE_GRADE_PROFILE, pricing)
    matrix, judge_grades = [], []
    totals_by_candidate = {cid: 0.0 for cid in candidate_ids}
    judge_total = 0.0
    for task in tasks:
        for cid in candidate_ids:
            est = estimate_dispatch_usd(cid, task["size_profile"], pricing)
            matrix.append({"task_id": task["task_id"], "candidate": cid, "estimated_usd": est})
            totals_by_candidate[cid] += est

            judge_grades.append(
                {"task_id": task["task_id"], "candidate": cid, "estimated_usd": judge_unit_cost}
            )
            judge_total += judge_unit_cost

    grand_total = sum(totals_by_candidate.values()) + judge_total

    # T18: derived from the store's OWN recorded actuals, never from `matrix`/`totals` above --
    # the raw estimate stays exactly what `task_profiles` says (GUARDRAILS: report, never
    # silently adjust). A caller that passed no `store_dir` gets the same "no calibration
    # data" shape an empty store would -- absence is never a silent omission (T18 do-3).
    calibration = build_calibration(store_dir)

    return {
        "repo": str(target_repo),
        "base_commit": base_commit,
        "mode": resolved_mode,
        "mode_reason": reason,
        "tasks": task_summaries,
        "candidates": candidate_ids,
        "judge": judge_id,
        "matrix": matrix,
        "judge_grades": judge_grades,
        "totals": {
            "by_candidate": totals_by_candidate,
            "judge_total": judge_total,
            "grand_total": grand_total,
        },
        "labels": labels,
        "notes": mining_notes,
        "calibration": calibration,
    }


def render_plan_markdown(card):
    """The plan card as markdown -- matrix table, totals, and the "go live" hint. `cmd_plan`
    and `cmd_run`'s refusal paths both render through this so the two never drift apart."""
    lines = [f"# repo-bench plan — {card['repo']}", ""]
    lines.append(f"base commit: {card['base_commit']}")
    lines.append(f"mode: {card['mode']} — {card['mode_reason']}")
    lines.append(f"candidates: {', '.join(card['candidates']) or '(none)'}")
    lines.append(f"judge: {card['judge']}")
    lines.append("")

    lines.append(f"## tasks ({len(card['tasks'])})")
    for t in card["tasks"]:
        lines.append(
            f"  - {t['task_id']}  size={t['size_profile']}  "
            f"oracle_tests_available={t['oracle_tests_available']}"
        )
    lines.append("")

    lines.append("## matrix (estimated USD per dispatch)")
    candidates = card["candidates"]
    by_task = {}
    for row in card["matrix"]:
        by_task.setdefault(row["task_id"], {})[row["candidate"]] = row["estimated_usd"]
    header = "| task | " + " | ".join(candidates) + " |"
    lines.append(header)
    lines.append("|" + "---|" * (len(candidates) + 1))
    for t in card["tasks"]:
        tid = t["task_id"]
        cells = [f"${by_task.get(tid, {}).get(cid, 0.0):.4f}" for cid in candidates]
        lines.append(f"| {tid} | " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("## totals")
    for cid in candidates:
        lines.append(f"  {cid}: ${card['totals']['by_candidate'].get(cid, 0.0):.4f}")
    lines.append(f"  judge grading ({len(card['judge_grades'])} grades): "
                  f"${card['totals']['judge_total']:.4f}")
    lines.append(f"  grand total: ${card['totals']['grand_total']:.4f}")
    lines.append("")

    # T18: how wrong the estimates above have measured against this store's own recorded
    # actuals -- ALWAYS printed, never omitted, whether there is history or not (do-3).
    calibration = card.get("calibration") or {"labels": [CALIBRATION_NONE_LABEL]}
    lines.append("## calibration (task_profiles accuracy vs. this store's own recorded actuals)")
    for label in calibration.get("labels") or [CALIBRATION_NONE_LABEL]:
        lines.append(f"  {label}")
    lines.append("")

    for label in card["labels"]:
        lines.append(f"label: {label}")
    for note in card["notes"]:
        lines.append(f"note: {note}")
    lines.append("")
    lines.append("to spend: rerun with run --live --max-usd <ceiling>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------
# The harness seam and the live dispatch loop (PLAN D1/D2) -- THE ONE PLACE IN THIS REPO WHERE
# REAL MONEY COULD EVER MOVE. Three structural properties hold here or nowhere:
#   1. every dispatch goes through an INJECTABLE runner callable (`runner(argv, cwd)`), so a
#      test can exercise the whole loop end to end without a binary, a network, or a cent;
#   2. the ceiling is re-checked through `validate_ceiling` BEFORE every single dispatch --
#      never against a raw `args.max_usd`, never with a locally re-derived finiteness test;
#   3. the argv shape is `claude_execute`'s, reused verbatim, never re-derived here.

#: Appended to every dispatch argv so the harness emits a machine-readable result envelope we
#: can read token counts out of (`extract_usage`). ONE constant, MEDIUM confidence -- the exact
#: precedent set by `claude_execute.PERMISSION_FLAG`: it is best-effort against the CLI's
#: documented headless surface and deliberately NOT live-verified, because verifying it would
#: spend tokens (PLAN R1: never probe the real CLI to check a flag). If reality disagrees, the
#: correction is this ONE line edited against the CLI docs -- never a redesign, never a live
#: probe -- and the degradation path (plan estimate + `spend basis: estimated`) already covers
#: a parse miss without inventing a number.
OUTPUT_FORMAT_ARGS = ("--output-format", "json")

#: The harness binary name a dispatch argv starts with. Mirrors `claude_execute`'s
#: `--claude-bin` default so tests can point BOTH at the same temporary stub executable; no
#: test in this repo ever leaves it pointing at the real binary.
DEFAULT_CLAUDE_BIN = "claude"

#: Usage keys read out of a harness result envelope, in the CLI's own result shape. Absent
#: keys are simply absent from the extracted dict (never zero-filled: a fabricated zero is a
#: guess); `input_tokens`/`output_tokens` are required or the whole extraction fails to None.
USAGE_TOKEN_KEYS = (
    "input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
)

#: The pinned dispatch-record key set (PLAN D8: the store is self-describing). A `cells` entry
#: in results.json is one of these plus `estimated_usd` and `skipped`.
DISPATCH_RECORD_KEYS = frozenset({
    "task_id", "model", "wall_seconds", "usage", "usd", "usd_basis", "patch", "dispatch_rc",
})

#: The one reason a cell can be skipped in this task, and the envelope label that must ride
#: with it (PLAN D1: a ceiling stop is stated plainly and labels the results partial).
SKIPPED_COST_CEILING = "cost-ceiling"
COST_CEILING_LABEL = "partial (cost-ceiling)"

#: Spend-basis vocabulary and the honesty label each one carries (GUARDRAILS: "a dollar figure
#: printed without a basis or label beside it" is the drift signal).
SPEND_BASIS_LABELS = {
    "actual": (
        "spend basis: actual — every dispatched cell priced from harness-reported token "
        "counts at run time"
    ),
    "estimated": (
        "spend basis: estimated — no harness usage was extractable; dollars are task_profiles "
        "estimates, not a bill"
    ),
    "mixed": (
        "spend basis: mixed — some cells priced from harness-reported token counts, others "
        "fell back to task_profiles estimates (see each cell's usd_basis)"
    ),
}

#: F3 (Phase 2 review): the ceiling is a PRE-dispatch projection, so recorded spend CAN land
#: above it -- a dispatch's real cost is unknown until it returns. The overshoot is
#: unavoidable; rendering it identically to a clean preventive stop is not. Whenever recorded
#: spend exceeds the ceiling the envelope carries this label, in the vocabulary GUARDRAILS
#: pins: no dollar figure without its basis and its label.
OVERSPEND_LABEL_PREFIX = "overspend"

#: F6 (Phase 2 review): the envelope is the ONE artifact PLAN D8 says must always carry the
#: honesty labels, so it is written from a `finally` -- and when the loop did not get to the
#: end, the envelope says THAT too rather than reading as a completed run with fewer cells.
ABORTED_LABEL = (
    "partial (aborted) — the dispatch loop raised before completing; cells that never ran are "
    "absent from this envelope entirely, not recorded as skipped"
)
ABORTED_NOTE = (
    "the dispatch loop did not complete: this envelope was written from a finally block so the "
    "run still carries its spend, its basis and its labels — read the cell list as partial"
)

#: F3 (Phase 3 review): judge grading is a SPENDING step that T7 placed above the envelope
#: write, so a raising judge dispatch destroyed the one artifact D8 says must always carry
#: spend, basis and labels -- after real candidate money had been spent. Grading now runs in
#: its own guarded block; when it raises, the run says so here rather than vanishing.
GRADING_FAILED_LABEL = (
    "partial (grading failed) — judge grading raised before every cell was graded; the grades "
    "list is partial and the missing ones are absent, not `n/a`"
)
GRADING_FAILED_NOTE = (
    "judge grading raised and was abandoned; candidate dispatches and their recorded spend are "
    "unaffected and this envelope was still written"
)

#: Same rule one step later: the store's sibling files (`tasks/`, `dispatches/`, `plan.json`)
#: are written after grading, and a failure THERE must not cost the envelope either.
STORE_WRITE_FAILED_LABEL = (
    "partial (store writes failed) — some of tasks/, dispatches/ or plan.json is missing from "
    "this run dir; the envelope below is still complete"
)
STORE_WRITE_FAILED_NOTE = "writing the run dir's task/dispatch/plan records raised"

#: F1 (Phase 2 review): `--keep-work` keeps every cell sandbox in place for the whole run,
#: which is exactly the inter-cell isolation the sweep provides. Printed, loudly, whenever the
#: flag is used -- a debugging convenience must never quietly become a measurement condition.
KEEP_WORK_WARNING = (
    "WARNING: --keep-work keeps every cell sandbox under <run-dir>/work for the whole run, "
    "which DISABLES inter-cell leak isolation: a later candidate can read an earlier "
    "candidate's captured work out of a sibling sandbox one directory up. Use it to debug the "
    "harness, never for a measurement run."
)


def _overspend_label(spent_usd, ceiling_usd):
    """The F3 label: recorded spend went past the ceiling, said plainly, with both figures."""
    return (
        f"{OVERSPEND_LABEL_PREFIX}: recorded spend ${spent_usd:.4f} EXCEEDED the --max-usd "
        f"ceiling ${ceiling_usd:.4f} — the ceiling is checked before every dispatch, and a "
        f"dispatch's real cost is not known until it returns, so it can stop the NEXT dispatch "
        f"but cannot refund the last one"
    )


def default_dispatch_runner(argv, cwd):
    """The ONLY code path in this module that can invoke a real harness binary -> (rc, output).

    Reachable exclusively from `run` behind BOTH `--live` and a `validate_ceiling`-approved
    `--max-usd`, and overridable by every caller through `runner=`. No test and no verify
    command in this repo takes this path: they all inject a stub, so an accidental real
    dispatch is not something a test can do by forgetting a flag.
    """
    proc = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def build_claude_argv(claude_bin, model_id, prompt):
    """The dispatch argv: `claude_execute.build_dispatch` VERBATIM + `OUTPUT_FORMAT_ARGS`.

    Reuse, never fork (PLAN D2): the `-p` / `--model` / permission-flag shape belongs to
    `claude_execute` and is never re-derived here -- this module adds exactly one thing to it,
    the output format it needs in order to read token counts back.
    """
    return _ce().build_dispatch(claude_bin, model_id, prompt, extra_args=OUTPUT_FORMAT_ARGS)


def argv_carries_output_format(argv):
    """True when `OUTPUT_FORMAT_ARGS` appears CONSECUTIVELY in a dispatch argv.

    A flag and its value separated by anything else is not the same command line, so this
    checks adjacency rather than membership -- it is the assertion the demo and the safety
    tests make about every argv the runner ever sees.
    """
    argv = list(argv)
    n = len(OUTPUT_FORMAT_ARGS)
    return any(
        tuple(argv[i:i + n]) == OUTPUT_FORMAT_ARGS for i in range(len(argv) - n + 1)
    )


def _json_objects(text):
    """Yield every top-level JSON object embedded anywhere in `text`, left to right.

    Harness output is not guaranteed to be pure JSON (warnings, banners, a trailing newline),
    so this scans rather than parsing the whole string -- and it never raises: a `{` that
    starts nothing parseable is simply skipped.
    """
    decoder = json.JSONDecoder()
    idx = 0
    while True:
        start = text.find("{", idx)
        if start < 0:
            return
        try:
            obj, end = decoder.raw_decode(text, start)
        except ValueError:
            idx = start + 1
            continue
        idx = max(end, start + 1)
        yield obj


def extract_usage(output):
    """Token counts out of a harness result envelope -> dict, or None. NEVER a guess.

    Best-effort by design (PLAN D2/R1): the LAST JSON object carrying a `usage` mapping wins
    (the result envelope is emitted last). ANY failure -- no JSON at all, no `usage`, a
    non-numeric count, missing input/output totals -- returns None, and the caller degrades to
    the plan estimate with `usd_basis: "estimated"`. Guessing a token count would put a
    fabricated dollar figure into the store, which is the one thing the store must never hold.
    """
    if not output:
        return None
    usage = None
    for obj in _json_objects(output):
        if isinstance(obj, dict) and isinstance(obj.get("usage"), dict):
            usage = obj["usage"]
    if usage is None:
        return None

    extracted = {}
    for key in USAGE_TOKEN_KEYS:
        value = usage.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        extracted[key] = value
    if "input_tokens" not in extracted or "output_tokens" not in extracted:
        return None
    return extracted


#: Harness usage key -> the key `cost_report.price` reads the same quantity under. The two
#: vocabularies differ because the harness's result envelope and the transcript records
#: `cost_report` was written for name identical things differently; TRANSLATING NAMES IS THE
#: ONLY THING THIS MODULE IS ALLOWED TO DO WITH PRICING (PLAN D10 -- the rates, the cache
#: multipliers and every division live in `cost_report` + `data/pricing.json`, and a term-for-
#: term re-implementation of `price()` here is a fork of the sharpest fence in the kit).
USAGE_KEY_MAP = (
    ("input_tokens", "input"),
    ("output_tokens", "output"),
    ("cache_read_input_tokens", "cache_read"),
    ("cache_creation_input_tokens", "cache_write"),
)


def price_usage(model_id, usage, pricing):
    """Price harness-reported token counts -> USD, or None when they cannot be priced honestly.

    A KEY-MAPPING WRAPPER around `cost_report.price` (PLAN D10 / F7): `USAGE_KEY_MAP` renames
    the harness's counts into the shape `price()` reads, `price()` does the arithmetic, and
    that is the whole of it. Absent counts map to 0 -- `price()` subscripts all four, and a
    count the harness did not report is genuinely zero tokens of that kind, not a guess.

    `price()` also subscripts the pricing dict for its cache multipliers, so a pricing dict
    missing a number it needs raises `KeyError` -- caught here and returned as None, which
    preserves this function's contract exactly: the caller records the plan estimate and says
    `estimated` rather than silently dropping (or inventing a ratio for) part of the bill. An
    unpriceable MODEL is a different thing and still raises: that is a caller bug, not a gap
    in the pricing file.
    """
    if not usage:
        return None
    cr = _cr()
    key = cr.match_model(model_id, pricing)
    if key is None:
        raise KeyError(
            f"repo_bench cannot price model id {model_id!r}: cost_report.match_model found no "
            f"entry in data/pricing.json (valid ids: {', '.join(pricing['models'])})"
        )
    mapped = {dest: (usage.get(src) or 0) for src, dest in USAGE_KEY_MAP}
    try:
        return cr.price(key, mapped, datetime.now(timezone.utc), pricing)
    except KeyError:
        return None


def claude_pricing_loader():
    """PLAN D2's FOURTH adapter member: where this harness's dollars come from.

    Claude's numbers are `data/pricing.json`, reached through `cost_report.load_pricing()` --
    the single numeric source of truth, whose path this module never re-derives. It is an
    adapter MEMBER rather than a `_cr().load_pricing()` call hardwired into `dispatch_cell`
    and `cmd_run` because a seam you have to edit in order to use is not a seam (F4): a
    codex/copilot adapter must be able to bring its own pricing file without either function
    changing. No such adapter is built here -- that is kit OUT-OF-SCOPE; the stub adapter in
    the tests is what proves the seam.
    """
    return _cr().load_pricing()


#: The Claude harness adapter (PLAN D2). A plain dict, deliberately: it is the seam a
#: codex/copilot adapter drops into later WITHOUT this module learning anything about them --
#: `name` for the envelope, `build_argv(bin_, model_id, prompt)` for the argv shape,
#: `extract_usage(output)` for the token counts, `load_pricing()` for the numbers those counts
#: are priced against. No codex/copilot adapter is built here (kit OUT-OF-SCOPE); tests
#: exercise the seam with a stub adapter instead.
CLAUDE_ADAPTER = {
    "name": "claude",
    "build_argv": build_claude_argv,
    "extract_usage": extract_usage,
    "load_pricing": claude_pricing_loader,
}


def would_exceed_ceiling(spent_usd, next_estimate_usd, max_usd):
    """PLAN D1's pre-dispatch ceiling check: would this next dispatch cross `--max-usd`?

    Calls `validate_ceiling` on EVERY invocation, deliberately. That helper exists because
    `--max-usd nan` parses cleanly through argparse and then defeats `x > ceiling` outright
    (IEEE-754), and a guard checked in two places is a guard that will eventually be checked
    two different ways -- so this, the per-dispatch check, re-uses the same named helper the
    CLI gate uses rather than re-deriving a finiteness test or comparing against a raw
    `args.max_usd`. A missing ceiling here is not a permissive default; it is a refusal.
    """
    ceiling = validate_ceiling(max_usd)
    if ceiling is None:
        raise ValueError(
            "refusing to dispatch: no --max-usd ceiling is in force (PLAN D1 -- every "
            "dispatch is ceiling-checked; there is no unbounded run)"
        )
    return (spent_usd + next_estimate_usd) > ceiling


def prepare_cell_sandbox(task, target_repo, dest, git_runner=None, templates=None):
    """A fresh sandbox for ONE task x candidate cell -> (sandbox_info, baseline_commit).

    SETUP-PATCH LAW (see the module docstring) is enforced HERE, at the one place a candidate
    sandbox is built for dispatch: a general-mode task's bug lives only in its `setup_patch`,
    so a sandbox built off `base_commit` is GREEN until that patch is applied. The patch is
    applied and AMENDED INTO the root commit, which stays the baseline the candidate's patch
    is captured against -- so the injected bug is part of the base state and never appears
    inside the candidate's diff. Issue-replay tasks carry `setup_patch: None` and keep the
    root commit untouched.

    THE SANDBOX'S OWN HISTORY IS NOT A CHANNEL (T5R2). Committing the setup patch ON TOP of
    the root commit left TWO commits in the candidate's working directory, and
    `git diff HEAD~1 HEAD` reversed IS the general-mode answer -- the bug was readable with
    `git log -p` from inside the candidate's own cwd, which made general-mode measurement
    worthless no matter how clean the ancestry above it was. `--amend` leaves exactly one
    commit; `SANDBOX_LOCAL_CONFIG` means the amend leaves no reflog entry either; and
    `git prune --expire=now` drops the now-unreachable pre-amend commit, tree and blobs, so
    the clean source cannot be recovered from a dangling object with `git fsck` or
    `git cat-file --batch-all-objects`. All three are needed: any one alone still hands the
    candidate a diff between clean and buggy.

    THE PATCH FILE NEVER TOUCHES THE RUN DIR (F1). It is written into a system temp dir of its
    own and unlinked the instant `git apply` returns. Inside the sandbox it would read as the
    candidate's own work; anywhere under the run dir it would sit one `../` from the
    candidate's cwd, and REVERSING a setup patch is the general-mode answer -- a candidate
    running with permissions bypassed only has to `cat` it. There is deliberately no
    caller-supplied directory for it any more: an optional "put it here" seam is a leak
    waiting for the next caller to re-open.

    `templates` (T17) is a `GradeTemplates` cache or None. None is the whole of today's
    behaviour, byte for byte. When it is supplied, the prepared `--setup-cmd` ARTIFACTS are
    overlaid LAST, on top of the finished base state -- after the setup patch has been amended
    into the root commit, so none of the leak-closing machinery above is disturbed and the
    overlay is purely additive. `cmd_run` passes a cache only when building a GRADE substrate,
    never when building a candidate's own sandbox: setup is arbitrary code bought for grading
    (PLAN D11), and the candidate's tree is not an input to any grade.
    """
    info = make_sandbox(target_repo, task["base_commit"], dest, git_runner=git_runner)
    sandbox = Path(info["path"])
    baseline = info["init_commit"]

    setup_patch = task.get("setup_patch")
    if setup_patch:
        with tempfile.TemporaryDirectory(prefix="repo-bench-setup-") as holder:
            patch_file = Path(holder) / f"{task['task_id']}.setup.patch"
            patch_file.write_text(setup_patch)
            rc, out = git_sandbox(sandbox, "apply", str(patch_file), git_runner=git_runner)
            patch_file.unlink()
        _require_ok(rc, out, f"git apply setup_patch for {task['task_id']} in {sandbox}")
        rc, out = git_sandbox(sandbox, "add", "-A", git_runner=git_runner)
        _require_ok(rc, out, f"git add after setup_patch in {sandbox}")
        # `--amend`, not a second commit: one root commit, nothing to diff against. The
        # message stays SANDBOX_INIT_MESSAGE -- the old "task's bug injected" wording was
        # only ever seen alongside a second commit, and as the SOLE commit message in the
        # candidate's repo it is a free tell about how the task was built.
        rc, out = git_sandbox(
            sandbox, "commit", "-q", "--amend", "-m", SANDBOX_INIT_MESSAGE,
            git_runner=git_runner,
        )
        _require_ok(rc, out, f"git commit --amend after setup_patch in {sandbox}")
        rc, out = git_sandbox(sandbox, "prune", "--expire=now", git_runner=git_runner)
        _require_ok(rc, out, f"git prune after setup_patch in {sandbox}")
        rc, out = git_sandbox(sandbox, "rev-parse", "HEAD", git_runner=git_runner)
        _require_ok(rc, out, f"git rev-parse after setup_patch in {sandbox}")
        baseline = out.strip()
        # The amended commit IS the sandbox's root now, so this is what
        # `sandbox_init_commit` derives and what `capture_patch` baselines against. Leaving
        # the pre-amend hash here would be a dangling reference to an object `git prune` has
        # already deleted -- and, before the prune ran, a baseline that would have reported
        # the injected bug as the candidate's own work.
        info["init_commit"] = baseline

    if templates is not None:
        templates.overlay(task, sandbox)

    return info, baseline


# ---------------------------------------------------------------------------------------------
# T17 -- PREPARED GRADE TEMPLATES: making a target with a build/install step benchmarkable.
#
# A sandbox is a `git archive` tree extraction with no `node_modules`, no `.venv`, no build
# output. On a target whose tests cannot run until something is installed, EVERY grading would
# have to install first -- ~30 installs where the problem was 30 test runs, which is worse than
# the problem. So the install runs ONCE per template and every grade substrate reuses its
# artifacts.
#
# THREE PROPERTIES MAKE THAT SAFE, AND ALL THREE ARE LOAD-BEARING. They point in different
# directions, and the kit has had to rediscover each of them from a working forgery:
#
#   1. NO CANDIDATE TREE, PATCH OR PATH IS AN INPUT TO PREPARING A TEMPLATE. Preparation reads
#      the task record and the target repo's base state (through `prepare_cell_sandbox`, the
#      same function that builds the candidate's own sandbox) and nothing else -- there is no
#      parameter, no default and no fallback through which a candidate's work could reach it.
#      That is the whole of the claim, and it is checkable by reading `_prepare`'s inputs.
#
#      (This used to be stated as a TEMPORAL claim -- that a template exists before any
#      candidate for its task has been dispatched -- and that claim was FALSE, load-bearingly
#      so: templates are prepared LAZILY, inside grading, which runs AFTER `dispatch_cell`. The
#      first cell of a task sees no template; every later cell of the run does. That sentence is
#      why the store's LIFETIME hazard below looked impossible to every reader, including the
#      one who wrote the remediation brief. A temporal safety claim has to be true of the
#      timeline; the data-flow claim above is what actually holds, and it is the one that
#      matters.)
#
#      The whitelist invariant is therefore unchanged, restated with a template in play:
#
#          grade substrate = (pristine base state + setup artifacts)
#                            + the candidate's IN-SCOPE patch
#                            + the reference test blobs
#          and nothing else.
#
#   2. NOTHING IN A TEMPLATE TELLS A CANDIDATE ANYTHING ITS OWN SANDBOX DOES NOT. A template
#      built from the PRISTINE base would be a brand-new answer key in general mode, where the
#      candidate's sandbox is base + the injected `setup_patch`: `diff` the two and the bug
#      falls out. Two things close that, together:
#        * the template's build tree is built through `prepare_cell_sandbox`, so it carries the
#          task's `setup_patch` too -- it is byte-for-byte the state the candidate STARTS in;
#        * the cache key includes that setup patch, so general-mode tasks (which share a base
#          commit but each carry a different injected bug) never share a template. That costs a
#          general-mode run one preparation per task, and it is the right trade: `--setup-key`
#          collapsing exists for issue-replay, where the bases differ and `setup_patch` is None.
#
#   3. THE CAPTURED ARTIFACTS ARE OUT OF A CANDIDATE'S REACH FOR THE WHOLE RUN, AND ARE
#      VERIFIED ANYWAY (T17R/F1+F3). Properties 1 and 2 are both about how a template is BUILT.
#      The hazard that actually shipped was its LIFETIME: the artifacts stayed on disk under
#      `<run-dir>/work/templates/<key>/artifacts` for the whole run, `overlay` re-read them from
#      disk on EVERY grading, and a candidate's cwd is `<run-dir>/work/cell-NNN`. One `../` and
#      the store was writable. A cell that changed NOTHING in its own sandbox could overwrite
#      `vendor/dep.py` (`node_modules/<pkg>/index.js` on a real target), have `overlay` copy
#      those bytes into its own grade substrate, and read `passed: True` with both evidence
#      fields empty -- a forged objective cell, counting toward the D7 floor and eligible for
#      `apply`. In the READ direction the same store was a cross-task answer key: task 2's
#      candidate could read task 1's pristine build output.
#
#      Closed twice, independently, because this is the sixth ring of this leak family and
#      every previous single fix was one ring short:
#        * the SETUP COMMAND still executes under `<run-dir>/work/templates/<key>/build` (that
#          is the arbitrary-code mutation PLAN D11 governs, and it stays where D3/D11 put it),
#          but the CAPTURED BYTES are moved out of the run dir entirely, into a private
#          0700 system temp directory whose name is in no file the candidate can read, and the
#          build tree is deleted the moment the capture is done. Anything under the run dir is
#          reachable with `../..`, so relocating within it would not have been a fix; this is
#          the T7R carve-out exactly (the judge's dispatch cwd was moved out of the run dir for
#          the same reason, and for the same kind of thing: inert grading material, no target
#          mutation). Stated honestly and NOT overclaimed: this defeats relative traversal from
#          a sandbox and any path a candidate could read off disk -- it is not a sandbox, and a
#          candidate that trawls the system temp dir is not stopped by it. That is exactly why
#          there is a second mechanism.
#        * every captured artifact is CONTENT-HASHED at capture and re-verified before EVERY
#          overlay. A mismatch is refused, never repaired: the tests oracle renders
#          `available: False` with `ARTIFACT_TAMPERED_NOTE` and the run is labelled. Absence,
#          not failure (PLAN D5) -- a tampered store is a measurement that did not happen, not a
#          candidate that got it wrong.

#: The honesty rule this whole feature turns on (PLAN D5): a toolchain that would not build is
#: an ABSENT oracle, never a candidate that failed. `passed` stays None.
SETUP_FAILED_NOTE = (
    "the --setup-cmd for this task's grade template failed — the tests oracle is UNAVAILABLE "
    "for every grading that depended on that template; a build that does not build is absence, "
    "not a candidate that failed to solve anything"
)

SETUP_FAILED_LABEL = (
    "partial (setup failed) — one or more --setup-cmd grade templates could not be prepared; "
    "every grading that depended on them renders n/a, never a failure"
)

#: `--setup-cmd` only ever runs to make the TESTS oracle runnable. Without `--test-cmd` there is
#: no tests oracle, so no template is ever prepared and the setup command never runs -- said out
#: loud rather than silently doing nothing.
SETUP_WITHOUT_TEST_CMD_NOTE = (
    "--setup-cmd was supplied without --test-cmd: the tests oracle is unavailable either way, "
    "so no grade template is prepared and the setup command never runs"
)

#: Plan-time only. `plan` spends nothing and runs nothing -- including this.
SETUP_PLAN_NOTE = (
    "a --setup-cmd is configured; it is NOT run by `plan` — during `run` it runs once per grade "
    "template (never in a candidate's sandbox) and every grade substrate reuses its artifacts"
)

#: T17R/F1 -- the second, independent mechanism. A store whose bytes changed between capture and
#: overlay is not a store any grade may be built from, and the honest reading is ABSENCE: the
#: measurement did not happen. Repairing it silently, or grading anyway, is how a forged `solved`
#: gets in.
ARTIFACT_TAMPERED_NOTE = (
    "the prepared --setup-cmd artifacts for this task's grade template do not match the content "
    "hashes taken when they were captured — the tests oracle is UNAVAILABLE for every grading "
    "that depended on that template; a grade substrate is never built from bytes that changed "
    "after capture, and a store that changed is absence, not a candidate that failed"
)

ARTIFACT_TAMPERED_LABEL = (
    "partial (setup artifacts failed verification) — one or more --setup-cmd artifact stores "
    "changed between capture and overlay; every grading that depended on them renders n/a, "
    "never a failure"
)

#: T17R/F1+F3 -- where the captured bytes live, said out loud in the envelope. The path itself is
#: deliberately NOT recorded: naming it in a file under the run dir would undo the move.
ARTIFACT_STORE_NOTE = (
    "captured --setup-cmd artifacts are held OUTSIDE the run dir, in a private system temp "
    "directory deleted when the run ends (the setup command itself still runs under "
    "<run-dir>/work/templates/<key>/build) — a candidate's cwd is under the run dir, so a store "
    "kept there is one `../` from every candidate for the whole run; artifacts are content-"
    "hashed at capture and re-verified before every overlay"
)

#: T17R/F2 -- `--setup-key` is sound only when the setup output is a function of the keyed paths
#: alone. True for a dependency install; FALSE for any compile, where the output is a function of
#: the SOURCE, which differs between two tasks' base commits. Both refusals below keep the
#: sharing decision structural rather than leaving it to documentation.
SHARING_REFUSED_TRACKED_NOTE = (
    "--setup-key sharing refused for task {task_id}: the template's artifacts include path(s) "
    "tracked at a base commit ({paths}) — a rewritten tracked file is build output, not a "
    "shareable install artifact, so this task was given its own prepared template"
)

SHARING_REFUSED_MISMATCH_NOTE = (
    "--setup-key sharing refused for task {task_id}: preparing the same keyed template at this "
    "task's own base commit produced DIFFERENT artifacts, so the setup output depends on the "
    "source and not on the keyed paths alone (a compile, not an install) — this task and every "
    "later task with a different base commit gets its own prepared template"
)

SHARING_VERIFIED_NOTE = (
    "--setup-key sharing verified for template {key}: preparing it again at a second, different "
    "base commit produced byte-identical artifacts, so the keyed template is reused from here "
    "on — evidence that this setup output is source-independent, not a guarantee of it"
)

SHARING_PROBE_ROLE = "cross-base verification probe (T17R/F2)"

#: T17R/F7 -- a `--setup-key` path that does not exist at a task's base commit carries no
#: content, so keying on it would collapse EVERY such task onto one template: the maximum-
#: amplitude case of F2, reachable by a single typo. The key falls back to the base commit
#: instead (no collapse) and the run says so loudly.
SETUP_KEY_ABSENT_LABEL = (
    "--setup-key path(s) absent at one or more base commits — those tasks were keyed on their "
    "base commit instead of collapsing onto a shared template; check the path spelling"
)


def _tree_index(root):
    """`relpath -> (kind, ...)` for every entry under `root`, `.git` pruned.

    The snapshot `--setup-cmd`'s artifacts are derived from: run it before and after setup and
    the difference IS the install. Symlinks are recorded by their target and never descended
    (a `node_modules/.bin` cycle must not walk forever), and file identity is
    `(size, mtime_ns)` -- enough to notice a setup step that REWRITES a tracked file, without
    hashing a dependency tree.
    """
    root = Path(root)
    index = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = Path(dirpath).relative_to(root)
        prefix = "" if not rel_dir.parts else f"{rel_dir.as_posix()}/"
        kept = []
        for name in dirnames:
            if name == ".git":
                continue
            path = Path(dirpath) / name
            rel = prefix + name
            if path.is_symlink():
                index[rel] = ("symlink", os.readlink(path))
            else:
                index[rel] = ("dir",)
                kept.append(name)
        dirnames[:] = kept
        for name in filenames:
            path = Path(dirpath) / name
            rel = prefix + name
            if path.is_symlink():
                index[rel] = ("symlink", os.readlink(path))
                continue
            try:
                st = path.stat()
            except OSError:  # pragma: no cover - a file that vanished mid-walk
                continue
            index[rel] = ("file", st.st_size, st.st_mtime_ns)
    return index


def _setup_artifact_paths(before, after):
    """Two `_tree_index` snapshots -> the minimal path set `--setup-cmd` created or changed.

    Collapsed at directory granularity: a directory that did not exist before setup is recorded
    as ITSELF and never descended, so `npm ci` yields `["node_modules"]` rather than thirty
    thousand paths. A file that already existed and changed is recorded individually.

    Known limit, stated rather than hidden: a setup step that DELETES a tracked file is not
    captured -- the artifact set only ever adds. No install this feature exists for does that.
    """
    changed = sorted(path for path, entry in after.items() if before.get(path) != entry)
    roots = []
    for path in changed:
        if after[path][0] != "dir" or path in before:
            continue
        if not any(path.startswith(f"{root}/") for root in roots):
            roots.append(path)
    out = list(roots)
    for path in changed:
        if after[path][0] == "dir":
            continue
        if any(path.startswith(f"{root}/") for root in roots):
            continue
        out.append(path)
    return sorted(set(out))


def _artifact_digest(path):
    """A content hash of ONE captured artifact entry (T17R/F1) -> hex digest, or None if gone.

    CONTENT, not `(size, mtime)`: `_tree_index` above is a change DETECTOR for a tree we own and
    just ran a command in, where cheap identity is enough; this is a TAMPER check on bytes that
    have to be trusted to produce a `solved`, and padding a forgery to the same length is not a
    difficulty. A directory artifact (`node_modules`) is hashed as its whole manifest --
    every path, kind, and file body, in sorted order -- so a single edited file anywhere under it
    changes the digest.

    The cost is one sequential read of the artifact set per grading, which is bounded by the same
    disk the install just wrote and is nothing beside the test command it precedes. Symlinks are
    hashed by their target and never followed (a `node_modules/.bin` cycle must not walk
    forever), which also means a symlink RE-POINTED at a candidate's file is caught here as
    surely as an edited file.
    """
    path = Path(path)
    h = hashlib.sha256()

    def feed(rel, entry):
        if entry.is_symlink():
            h.update(b"symlink\0" + rel.encode("utf-8") + b"\0"
                     + os.readlink(entry).encode("utf-8") + b"\0")
            return
        if entry.is_dir():
            h.update(b"dir\0" + rel.encode("utf-8") + b"\0")
            return
        h.update(b"file\0" + rel.encode("utf-8") + b"\0")
        with open(entry, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        h.update(b"\0")

    if not path.is_symlink() and not path.exists():
        return None
    if path.is_symlink() or not path.is_dir():
        feed("", path)
        return h.hexdigest()

    feed("", path)
    for dirpath, dirnames, filenames in os.walk(path, followlinks=False):
        rel_dir = Path(dirpath).relative_to(path)
        prefix = "" if not rel_dir.parts else f"{rel_dir.as_posix()}/"
        dirnames.sort()
        kept = []
        for name in dirnames:
            child = Path(dirpath) / name
            feed(prefix + name, child)
            if not child.is_symlink():
                kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            child = Path(dirpath) / name
            try:
                feed(prefix + name, child)
            except OSError:  # pragma: no cover - a file that vanished mid-walk
                h.update(b"unreadable\0" + (prefix + name).encode("utf-8") + b"\0")
    return h.hexdigest()


def _copy_artifact(src, dst):
    """Copy one captured artifact entry (file, directory or symlink) into a substrate."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_symlink():
        if dst.is_symlink() or dst.exists():
            dst.unlink()
        os.symlink(os.readlink(src), dst)
    elif src.is_dir():
        shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)


class GradeTemplates:
    """The `--setup-cmd` cache: prepare once, reuse for every grading (PLAN D5/D11; T17/T17R).

    Constructed by `cmd_run` ONLY when `--setup-cmd` was supplied; `templates=None` everywhere
    else keeps today's behaviour byte for byte. The three safety properties are argued in the
    section comment above this class -- read them before changing anything here.

    Preparation, per key, exactly once:
      1. `prepare_cell_sandbox(task, ...)` into `<root>/<key>/build` -- the SAME function that
         builds the candidate's own sandbox, so the template's starting tree and the candidate's
         cannot drift apart. Its inputs are the task record and the target repo: no candidate
         tree, patch or path is one of them.
      2. snapshot, run `--setup-cmd` through the SAME injectable runner seam `--test-cmd` uses
         (`runner(cmd, cwd) -> (rc, output)`), snapshot again.
      3. the difference is MOVED into this cache's PRIVATE ARTIFACT STORE -- a 0700 system temp
         directory OUTSIDE the run dir (T17R/F1+F3; `ARTIFACT_STORE_NOTE`) -- each entry is
         content-hashed, and the build tree is deleted. `cleanup()` removes the store when the
         run ends; a finalizer is registered as a backstop so a caller that forgets still leaves
         nothing behind.
    A non-zero rc records `ok: False` and is NOT retried -- re-running a failing install once
    per grading is the same pathology this class exists to remove -- and every grading that
    depends on it renders the tests oracle unavailable (`SETUP_FAILED_NOTE`), never failed.

    The key (PLAN-visible, reported, never a silent hash nobody can account for):
      * `--setup-key PATH` (repeatable) -> the BLOB IDS of those paths at the task's base
        commit, read through the read-only `git_target` choke point (`rev-parse <base>:<path>`,
        already on the allowlist). A blob id IS a content hash, so this is content-keyed without
        reading, decoding or storing any content -- and tasks whose dependency manifests match
        share one template even though their base commits differ. A path that does NOT exist at
        a task's base contributes no content, so keying on it alone would collapse every such
        task onto one template: the base commit is added back instead and the run is labelled
        (T17R/F7).
      * no `--setup-key` -> the base commit.
      * plus, always, the task's own `setup_patch` when it has one (general mode). See property
        2 above: sharing one template across different injected bugs would put a clean copy of
        the source one `../` from the candidate that has to find the bug.

    SHARING A KEY IS NOT THE SAME AS SHARING ARTIFACTS (T17R/F2). `--setup-key` is sound only
    when the setup output is a function of the keyed paths alone -- true of a dependency install,
    false of any compile, where it is a function of the SOURCE and two tasks' base commits differ
    by construction. Reproduced: two tasks sharing a key, task B's substrate carrying task A's
    `dist/app.py`, so B was graded against A's source and its own candidate patch was irrelevant.
    Two structural refusals, in cost order, before any artifact crosses a base commit:
      * if the artifacts include any path that EXISTS at either base commit, the setup step
        rewrote tracked content -- that is build output, and it is refused outright;
      * otherwise the template is PREPARED AGAIN at the second base and the two artifact sets are
        compared by digest. Identical -> the key is marked verified and every later task reuses
        it (one extra install for the whole run, not one per task). Different -> sharing is
        refused for the rest of the run and the probe becomes that task's own template, so the
        second install is not wasted either way.
    Verification is EVIDENCE, not proof: it says this setup output was reproducible across two
    bases, which is the same posture `candidate_modified_out_of_scope` takes. Every refusal and
    every verification is reported.

    Wall-clock is recorded here and ONLY here. Template preparation is toolchain time, not model
    latency: folding it into a cell's `wall_seconds` would charge whichever model happened to be
    graded first for the build, and oracle (d) is exactly what the daily-driver pick reads.
    """

    def __init__(self, target_repo, root, setup_cmd, test_runner=None, git_runner=None,
                 key_paths=()):
        self.target_repo = Path(target_repo)
        self.root = Path(root)
        self.setup_cmd = setup_cmd
        self.test_runner = test_runner or default_test_runner
        self.git_runner = git_runner
        self.key_paths = tuple(key_paths or ())
        self._records = {}
        self._store_root = None
        self._finalizer = None
        self._notes = []
        self._absent_key_paths = []
        self._exists_at_base = {}

    # -- the artifact store (T17R/F1) ------------------------------------------------------

    def store_root(self):
        """The private artifact store, created on first use.

        OUTSIDE the run dir on purpose, and by the same reasoning that moved the judge's
        dispatch cwd out of it (T7R): a candidate's cwd is `<run-dir>/work/cell-NNN`, so
        anything under the run dir -- at any depth -- is reachable with `../..` for the whole
        run, and this store is read on EVERY grading. The setup COMMAND still runs under the run
        dir (`self.root`), which is the arbitrary-code mutation PLAN D3/D11 governs; only the
        inert captured bytes live here. `tempfile.mkdtemp` gives 0700 and a name that appears in
        no file a candidate can read -- not a sandbox, and not claimed as one.
        """
        if self._store_root is None:
            self._store_root = Path(tempfile.mkdtemp(prefix="repo-bench-artifacts-"))
            self._finalizer = weakref.finalize(
                self, shutil.rmtree, str(self._store_root), True
            )
        return self._store_root

    def cleanup(self):
        """Delete the artifact store. `cmd_run` calls this in its `finally`, always -- including
        under `--keep-work`, which keeps the RUN DIR's working area and has no business
        resurrecting a store that deliberately does not live there."""
        if self._finalizer is not None:
            self._finalizer()
            self._finalizer = None
        self._store_root = None

    # -- keying ---------------------------------------------------------------------------

    def key_basis(self, task):
        """The human-readable facts a task's cache key is derived from (reported verbatim)."""
        base = task.get("base_commit")
        parts = []
        absent = []
        if self.key_paths:
            for path in sorted(set(self.key_paths)):
                rc, out = git_target(
                    self.target_repo, "rev-parse", f"{base}:{path}", git_runner=self.git_runner
                )
                if rc == 0:
                    parts.append(f"--setup-key {path} @ {out.strip()}")
                else:
                    absent.append(path)
                    parts.append(f"--setup-key {path} @ absent at this base commit")
        if absent or not self.key_paths:
            # F7: an absent key path is content-free, so a key built from it alone is identical
            # for every task carrying the same typo -- the maximum-amplitude form of F2. The
            # base commit goes back into the basis, which cannot collapse.
            parts.append(f"base commit {base}")
        for path in absent:
            entry = (path, base)
            if entry not in self._absent_key_paths:
                self._absent_key_paths.append(entry)
        setup_patch = task.get("setup_patch")
        if setup_patch:
            digest = hashlib.sha256(setup_patch.encode("utf-8")).hexdigest()[:12]
            parts.append(f"this task's mined setup patch {digest}")
        return parts

    @staticmethod
    def _key_of(basis):
        return hashlib.sha256("\n".join(basis).encode("utf-8")).hexdigest()[:16]

    def key_for(self, task):
        return self._key_of(self.key_basis(task))

    # -- preparation ----------------------------------------------------------------------

    def prepare(self, task):
        """The record for this task's template, preparing it the first time and never again.

        The cross-base sharing decision (T17R/F2) is taken HERE, before any artifact of another
        task's base commit can reach this task's substrate.
        """
        basis = self.key_basis(task)
        key = self._key_of(basis)
        record = self._records.get(key)
        if record is not None and record["base_commit"] != task.get("base_commit"):
            record = self._share_across_bases(basis, record, task)
        if record is None:
            record = self._prepare(key, basis, task)
            self._records[key] = record
        if task["task_id"] not in record["task_ids"]:
            record["task_ids"].append(task["task_id"])
        return record

    def _exists_at(self, base, path):
        """Is `path` present in the target's tree at `base`? (read-only `rev-parse`, cached)"""
        cached = self._exists_at_base.get((base, path))
        if cached is None:
            rc, _out = git_target(
                self.target_repo, "rev-parse", f"{base}:{path}", git_runner=self.git_runner
            )
            cached = rc == 0
            self._exists_at_base[(base, path)] = cached
        return cached

    def _share_across_bases(self, basis, record, task):
        """F2: may `record`'s artifacts be overlaid onto a task with a DIFFERENT base commit?"""
        base = task.get("base_commit")
        if record.get("share_verified"):
            return record
        if not record["ok"]:
            # A failed template has NO artifacts, so nothing can cross a base commit and F2
            # does not arise. Sharing the failure is also the honest cheap answer: re-running a
            # failing install once per base is the pathology this class exists to remove, and
            # every grading that depends on it renders the tests oracle unavailable either way.
            return record
        if not record.get("shareable", True):
            return self._dedicated(basis, task)

        tracked = sorted(
            rel for rel in record["artifacts"]
            if self._exists_at(record["base_commit"], rel) or self._exists_at(base, rel)
        )
        if tracked:
            record["shareable"] = False
            self._notes.append(SHARING_REFUSED_TRACKED_NOTE.format(
                task_id=task["task_id"], paths=", ".join(tracked)
            ))
            return self._dedicated(basis, task)

        probe = self._dedicated(basis, task, role=SHARING_PROBE_ROLE)
        if probe["ok"] and probe["artifact_digests"] == record["artifact_digests"]:
            record["share_verified"] = True
            self._notes.append(SHARING_VERIFIED_NOTE.format(key=record["key"]))
            return record
        record["shareable"] = False
        self._notes.append(SHARING_REFUSED_MISMATCH_NOTE.format(task_id=task["task_id"]))
        probe["role"] = None
        return probe

    def _dedicated(self, basis, task, role=None):
        """A template for THIS task's own base commit -- never shared with another base."""
        d_basis = list(basis) + [
            f"dedicated to base commit {task.get('base_commit')} (artifact sharing refused or "
            f"unverified across base commits — PLAN D5 / T17R F2)"
        ]
        d_key = self._key_of(d_basis)
        record = self._records.get(d_key)
        if record is None:
            record = self._prepare(d_key, d_basis, task)
            record["role"] = role
            self._records[d_key] = record
        return record

    def _prepare(self, key, basis, task):
        started = time.monotonic()
        build = self.root / key / "build"
        prepare_cell_sandbox(task, self.target_repo, build, git_runner=self.git_runner)

        before = _tree_index(build)
        setup_started = time.monotonic()
        rc, output = self.test_runner(self.setup_cmd, str(build))
        setup_seconds = time.monotonic() - setup_started

        store = self.store_root() / key
        record = {
            "key": key,
            "key_basis": list(basis),
            "base_commit": task.get("base_commit"),
            "task_ids": [],
            "path": str(store),
            "role": None,
            "ok": rc == 0,
            "rc": rc,
            "output_tail": (output or "").strip()[-400:],
            "artifacts": [],
            # T17R/F1: `rel -> sha256 of the captured bytes`, taken here and re-checked before
            # every overlay. Empty on a failed template (nothing was captured).
            "artifact_digests": {},
            "shareable": True,
            "share_verified": False,
            "tampered": [],
            "setup_seconds": setup_seconds,
            "prepare_seconds": 0.0,
            "gradings_served": 0,
        }

        if record["ok"]:
            store.mkdir(parents=True, exist_ok=True)
            for rel in _setup_artifact_paths(before, _tree_index(build)):
                dst = store / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(build / rel), str(dst))
                record["artifacts"].append(rel)
                record["artifact_digests"][rel] = _artifact_digest(dst)

        # The build tree is a second copy of the state the candidate starts in, and it has
        # served its whole purpose the moment the artifacts are out of it. The whole key
        # directory goes with it: what the install produced now lives outside the run dir
        # entirely (T17R/F1), so nothing of this template is left one `../` from a candidate.
        shutil.rmtree(self.root / key, ignore_errors=True)
        record["prepare_seconds"] = time.monotonic() - started
        return record

    # -- use ------------------------------------------------------------------------------

    def verify(self, record):
        """Re-hash a prepared template's artifacts -> the sorted paths that no longer match.

        Called before EVERY overlay, and by `oracle_tests` before it builds anything. An empty
        list is the only thing that may produce a grade; anything else is `available: False`
        with `ARTIFACT_TAMPERED_NOTE` (absence, never failure -- PLAN D5).
        """
        if not record["ok"]:
            return []
        store = Path(record["path"])
        bad = [
            rel for rel, digest in record["artifact_digests"].items()
            if _artifact_digest(store / rel) != digest
        ]
        for rel in bad:
            if rel not in record["tampered"]:
                record["tampered"].append(rel)
        return sorted(bad)

    def overlay(self, task, dest):
        """Copy this task's prepared artifacts into `dest` and count the reuse.

        Refuses on a failed template rather than silently overlaying nothing: a substrate built
        without the artifacts would run `--test-cmd` against an uninstalled tree and report a
        failure nobody measured. `oracle_tests` checks `prepare(...)["ok"]` and `verify(...)`
        first and renders the cell unavailable, so reaching either raise means a caller skipped
        those checks -- which is exactly why they are re-checked here rather than trusted.
        """
        record = self.prepare(task)
        if not record["ok"]:
            raise ValueError(f"{SETUP_FAILED_NOTE} (exit {record['rc']})")
        bad = self.verify(record)
        if bad:
            raise ValueError(f"{ARTIFACT_TAMPERED_NOTE} ({', '.join(bad)})")
        store = Path(record["path"])
        for rel in record["artifacts"]:
            src = store / rel
            if src.is_symlink() or src.exists():
                _copy_artifact(src, Path(dest) / rel)
        record["gradings_served"] += 1
        return record

    # -- reporting ------------------------------------------------------------------------

    def report(self):
        """What the envelope and the terminal line say. A cache that silently misses is
        indistinguishable from no cache, so the counts are not optional decoration -- and
        neither is a refused share, a verified one, or an artifact that failed verification."""
        records = [self._records[key] for key in sorted(self._records)]
        notes = list(self._notes)
        for path, base in self._absent_key_paths:
            notes.append(
                f"--setup-key {path} does not exist at base commit {base} — that task was keyed "
                f"on its base commit instead (T17R/F7: an absent path keys every task "
                f"identically, which is the maximum-amplitude form of the cross-task artifact "
                f"defect)"
            )
        return {
            "setup_cmd": self.setup_cmd,
            "setup_key_paths": list(self.key_paths),
            "templates_prepared": len(records),
            "templates_failed": sum(1 for r in records if not r["ok"]),
            "gradings_served": sum(r["gradings_served"] for r in records),
            "setup_seconds": round(sum(r["setup_seconds"] for r in records), 3),
            "prepare_seconds": round(sum(r["prepare_seconds"] for r in records), 3),
            # T17R/F1: the store's LOCATION is a property of the run worth recording; its PATH
            # is deliberately not, since this envelope lives under the run dir.
            "artifact_store_under_run_dir": False,
            "artifact_store_note": ARTIFACT_STORE_NOTE,
            "artifacts_tampered": sorted(
                f"{r['key']}:{rel}" for r in records for rel in r["tampered"]
            ),
            "key_paths_absent": [
                {"path": path, "base_commit": base} for path, base in self._absent_key_paths
            ],
            "sharing_notes": notes,
            "templates": [
                {
                    "key": r["key"],
                    "key_basis": list(r["key_basis"]),
                    "base_commit": r["base_commit"],
                    "task_ids": list(r["task_ids"]),
                    "role": r["role"],
                    "ok": r["ok"],
                    "rc": r["rc"],
                    "artifact_entries": len(r["artifacts"]),
                    "artifacts_tampered": list(r["tampered"]),
                    "shared_across_bases": bool(r["share_verified"]),
                    "gradings_served": r["gradings_served"],
                    "setup_seconds": round(r["setup_seconds"], 3),
                    "prepare_seconds": round(r["prepare_seconds"], 3),
                    "note": self._record_note(r),
                }
                for r in records
            ],
        }

    @staticmethod
    def _record_note(record):
        if not record["ok"]:
            return f"{SETUP_FAILED_NOTE} (exit {record['rc']})"
        if record["tampered"]:
            return f"{ARTIFACT_TAMPERED_NOTE} ({', '.join(sorted(record['tampered']))})"
        return None


def dispatch_cell(
    task, model_id, adapter, sandbox, runner=None, claude_bin=DEFAULT_CLAUDE_BIN,
    pricing=None, estimated_usd=None, baseline_commit=None, git_runner=None,
):
    """Run ONE task x candidate cell in an already-prepared sandbox -> a dispatch record.

    The prompt is `build_prompt`'s (leak-free by construction), the argv is the adapter's, and
    the dispatch itself goes through `runner(argv, cwd)` -- injectable, defaulting to
    `default_dispatch_runner` with `cwd=<sandbox>` so the candidate's whole world is the
    sandbox. Wall-clock is `time.monotonic` (never affected by a clock change mid-run).

    Dollars carry their basis, always: token counts extracted from the harness output price the
    cell as `actual`; ANY extraction or pricing miss falls back to the plan estimate and says
    `estimated`. There is no third path where a number appears without its basis. The pricing
    those counts are priced against comes from THE ADAPTER (`load_pricing`, PLAN D2's fourth
    member) -- never a hardwired `cost_report` call, which would price a future codex/copilot
    adapter's dispatches out of Claude's pricing file (F4).
    """
    if pricing is None:
        pricing = adapter["load_pricing"]()
    dispatch = runner or default_dispatch_runner
    sandbox_path = Path(sandbox)

    prompt = build_prompt(task)
    argv = adapter["build_argv"](claude_bin, model_id, prompt)

    started = time.monotonic()
    rc, output = dispatch(argv, str(sandbox_path))
    wall_seconds = time.monotonic() - started

    usage = adapter["extract_usage"](output or "")
    usd = price_usage(model_id, usage, pricing) if usage is not None else None
    if usd is None:
        usd, usd_basis = estimated_usd, "estimated"
    else:
        usd_basis = "actual"

    patch = capture_patch(sandbox_path, init_commit=baseline_commit, git_runner=git_runner)

    return {
        "task_id": task["task_id"],
        "model": model_id,
        "wall_seconds": wall_seconds,
        "usage": usage,
        "usd": usd,
        "usd_basis": usd_basis,
        "patch": patch,
        "dispatch_rc": rc,
    }


# ---------------------------------------------------------------------------------------------
# Oracle (c): the blind LLM judge (PLAN D6/T7). Bias-controlled by construction: the judge sees
# two patches labelled ONLY `Patch A` / `Patch B`, never told which is which; the slot
# assignment is randomized per grade and recorded for the audit trail either way -- parsed or
# not. `solved` NEVER comes from here (D5/R6); the judge's grade is always a labelled,
# subjective signal beside the objective tests oracle, never blended into it.

JUDGE_LABEL = "subjective LLM-judge grade vs reference — bias-controlled, not ground truth"
JUDGE_UNPARSEABLE_NOTE = "judge output unparseable"

#: F6 (Phase 3 review). `JUDGE_LABEL` says "bias-controlled" unqualified, and in general mode
#: that overstates it: the reference is BY CONSTRUCTION the exact inverse of one
#: `MUTATION_OPERATORS` entry -- one file, one line, ±1 -- while the candidate's patch is real
#: agent output. Nothing here is fixable structurally (that IS what a mutation-repair reference
#: is), so the honest move is to say so on every general-mode grade rather than let the label
#: imply a blinding strength the run does not have.
JUDGE_GENERAL_BLINDING_NOTE = (
    "general mode: blinding is materially weaker — the reference is a synthetic one-line "
    "inverse of a single mutation operator, which is a residual tell no slot randomisation "
    "removes"
)

#: F4c (Phase 3 review). A stripped reference that came out EMPTY (a tests-only fix commit, a
#: binary-only change, an unparseable/coloured diff) would render `Patch A` as nothing at all:
#: the pair deanonymises itself, the judge's grade is meaningless, and it parses cleanly enough
#: to be recorded as real. Skipping the dispatch is both the honest and the cheaper answer.
JUDGE_EMPTY_REFERENCE_NOTE = (
    "no judge grade dispatched — the reference patch is empty after stripping test hunks, so "
    "one slot would have rendered empty and deanonymised the pair"
)
SKIPPED_EMPTY_REFERENCE = "empty-reference"

#: The grammar `build_judge_prompt` demands and `parse_judge_output` looks for. Searched
#: anywhere in the judge's raw output (free-text rationale is expected around it, per the
#: prompt) -- never anchored to the whole string, only to this one line's shape.
JUDGE_GRADE_RE = re.compile(
    r"GRADE\s+A=(correct|partial|incorrect)\s+B=(correct|partial|incorrect)\s+"
    r"EQUIVALENT=(yes|no)",
    re.IGNORECASE,
)

JUDGE_PROMPT_INSTRUCTIONS = (
    "You are comparing two independently-produced patches for the issue above. Their origin "
    "is deliberately withheld from you -- grade them on their own merits.\n\n"
    "Respond with EXACTLY one line in this grammar (case-sensitive keywords, values from the "
    "listed vocabulary only), followed by your free-text rationale on the lines after it:\n\n"
    "GRADE A=<correct|partial|incorrect> B=<correct|partial|incorrect> EQUIVALENT=<yes|no>\n\n"
    "- A=/B= grade how well that patch fixes the issue.\n"
    "- EQUIVALENT=yes when the two patches are substantively the same fix; no otherwise.\n"
    "- The GRADE line must appear on its own line, in that exact grammar, before your "
    "rationale.\n"
)


def build_judge_prompt(task, reference_patch, candidate_patch, slot_seed):
    """The judge-facing prompt -> `(prompt, slots)` (PLAN D6).

    `slot_seed` (an int, 0 or 1) decides which of `Patch A` / `Patch B` holds the candidate --
    an even seed keeps A=candidate, an odd seed flips it, so two different seeds are guaranteed
    to disagree. `slots` (`{"A": "reference"|"candidate", "B": ...}`) is the audit record: it is
    returned regardless of what the judge ultimately says, so a grade is traceable back to which
    physical slot held which patch even when the judge's own output never parses.

    THE LEAK RULE, judge side: nothing in this prompt ever spells out which slot is which -- no
    occurrence of the words "reference" or "candidate" anywhere near a patch label. The two
    patches are handed in verbatim (any stripping -- e.g. withheld test hunks -- is the CALLER's
    job, `oracle_judge` below; this function composes whatever two patch strings it is given).
    """
    statement = (task.get("statement") or task.get("subject") or "").strip()
    if int(slot_seed) % 2 == 0:
        slot_a, slot_b = candidate_patch, reference_patch
        slots = {"A": "candidate", "B": "reference"}
    else:
        slot_a, slot_b = reference_patch, candidate_patch
        slots = {"A": "reference", "B": "candidate"}

    prompt = (
        f"{statement}\n\n"
        f"Patch A:\n{slot_a}\n\n"
        f"Patch B:\n{slot_b}\n\n"
        f"{JUDGE_PROMPT_INSTRUCTIONS}"
    )
    return prompt, slots


def parse_judge_output(output, slots):
    """The judge's raw output + the slot map it was dispatched with -> a grade dict, or `None`.

    Structural parse ONLY (PLAN D6): `JUDGE_GRADE_RE` must match somewhere in `output` or this
    returns `None` -- never a guessed/default grade (T7 item 3). On a match, the A/B letter
    grades are mapped back through `slots` to `candidate_grade`/`reference_grade` -- the WHOLE
    point of the blind slot design is that the grade must follow the SLOT, never the letter.
    """
    m = JUDGE_GRADE_RE.search(output or "")
    if not m:
        return None
    grade_a, grade_b, equivalent = m.group(1).lower(), m.group(2).lower(), m.group(3).lower()
    by_slot = {"A": grade_a, "B": grade_b}
    candidate_slot = next(s for s, who in slots.items() if who == "candidate")
    reference_slot = next(s for s, who in slots.items() if who == "reference")
    return {
        "candidate_grade": by_slot[candidate_slot],
        "reference_grade": by_slot[reference_slot],
        "equivalent": (equivalent == "yes"),
        "slots": dict(slots),
    }


def oracle_judge(
    task, reference_patch, candidate_patch, judge_model, adapter, runner, claude_bin, pricing,
    slot_seed=None, candidate_model=None, test_patterns=DEFAULT_TEST_PATTERNS,
):
    """Oracle (c) -- PLAN D6's blind, priced LLM judge -> a grade record.

    `slot_seed` defaults to `secrets.randbelow(2)` (the CLI's per-grade randomization; T7 item
    1) when not given -- tests pass a fixed 0/1 to make the assignment deterministic. Dispatch
    goes through the SAME `adapter`/`runner` seam every candidate cell uses, in a throwaway `cwd`
    of its own: grading needs no repo checkout, and a fresh, empty, unrelated directory can
    never become a channel between one candidate's sandbox and another's (T5R2 -- "no grading
    artifact may become reachable from a live candidate sandbox").

    THE JUDGE'S CWD IS NEVER UNDER THE RUN DIR (F1, Phase 3 review). T7 anchored it at
    `<run-dir>/work/repo-bench-judge-XXXX` on the reasoning that PLAN D3/D11 keep all scratch
    space under the run dir. That rule exists for CANDIDATE sandboxes and target mutation; the
    judge touches no target and works in an empty directory. What the anchoring bought instead
    was `../../tasks/<id>.json` (reference patch AND withheld test blobs) and
    `../../dispatches/<id>__<model>.json` (which MODEL wrote the patch in the other slot) two
    `cat`s away from a dispatch running with permissions bypassed. The judge is designed to see
    both patches -- that is grading -- but knowing which is the reference, and whose the other
    one is, is precisely the fact D6's blind slots exist to hide. There is deliberately no
    caller-supplied directory seam any more (the `prepare_cell_sandbox` precedent: an optional
    "put it here" is a leak waiting for the next caller to re-open); `cmd_run`'s buffering of
    the store writes past the grading pass is the second, independent leg of the same fix.

    THE CEILING IS NOT CHECKED HERE. Exactly like `dispatch_cell`, this function dispatches
    unconditionally the moment it is called -- `grade_cells` below is the caller that estimates
    and ceiling-checks BEFORE calling this, the same division of labour the candidate loop uses
    (`would_exceed_ceiling` in `cmd_run`, `dispatch_cell` unconditional beneath it).

    `judge ∈ candidates` is a HARD refusal already enforced at plan time (`build_plan`, T4) --
    this is the belt-and-braces RUNTIME check T7 item 4 asks for, redundant on purpose: if the
    caller supplies `candidate_model` (the model that produced `candidate_patch`) and it equals
    `judge_model`, this raises rather than silently grading a model against itself.

    P1-F5 + Nit (carried into T7): `reference_patch` is stripped of `test_patterns` file-blocks
    before it ever reaches the prompt -- the SAME leak the structural oracle already strips
    (`oracle_structural`). Unstripped, the judge sees one patch that adds tests and one that
    never does, which defeats the blind slot design as surely as naming the slots would.
    """
    if candidate_model is not None and judge_model == candidate_model:
        raise ValueError(
            f"repo_bench refuses to grade with judge_model == candidate_model "
            f"({judge_model!r}): PLAN D6 -- a judge grading its own patch is a hard refusal "
            f"(already enforced at plan time in build_plan; this is the belt-and-braces "
            f"runtime check inside oracle_judge)"
        )
    if slot_seed is None:
        slot_seed = secrets.randbelow(2)

    stripped_reference = _strip_test_hunks(reference_patch or "", test_patterns)
    prompt, slots = build_judge_prompt(task, stripped_reference, candidate_patch or "", slot_seed)
    argv = adapter["build_argv"](claude_bin, judge_model, prompt)

    dispatch = runner or default_dispatch_runner
    with tempfile.TemporaryDirectory(prefix="repo-bench-judge-") as cwd:
        rc, output = dispatch(argv, cwd)

    usage = adapter["extract_usage"](output or "")
    usd = price_usage(judge_model, usage, pricing) if usage is not None else None
    if usd is None:
        usd = estimate_dispatch_usd(judge_model, JUDGE_GRADE_PROFILE, pricing)
        usd_basis = "estimated"
    else:
        usd_basis = "actual"

    grade = parse_judge_output(output or "", slots)

    notes = []
    if grade is None:
        notes.append(JUDGE_UNPARSEABLE_NOTE)
    if (task.get("mode") if isinstance(task, dict) else None) == "general":
        notes.append(JUDGE_GENERAL_BLINDING_NOTE)

    return {
        "oracle": "judge",
        "judge_model": judge_model,
        "slots": dict(slots),
        "grade": grade,
        "usd": usd,
        "usd_basis": usd_basis,
        "label": JUDGE_LABEL,
        "notes": "; ".join(notes),
        "dispatch_rc": rc,
    }


def _skipped_grade(task_id, candidate_model, estimated_usd, reason=SKIPPED_COST_CEILING,
                   note=None):
    """A judge grade that was never dispatched -- same shape as a real grade, all-None where a
    dispatch would have put data (mirrors `_skipped_cell`: absence, never a zero).

    `reason` is the machine-readable vocabulary (`cost-ceiling`, `empty-reference`); `note`
    carries the sentence a reader needs when the reason alone would not explain itself (F4c).
    """
    return {
        "oracle": "judge",
        "task_id": task_id,
        "candidate_model": candidate_model,
        "judge_model": None,
        "slots": None,
        "grade": None,
        "usd": None,
        "usd_basis": None,
        "label": JUDGE_LABEL,
        "notes": note,
        "dispatch_rc": None,
        "estimated_usd": estimated_usd,
        "skipped": reason,
    }


def grade_cells(
    cells, tasks, judge_model, adapter, runner, claude_bin, pricing, spent_usd, max_usd,
    slot_seed=None, test_patterns=DEFAULT_TEST_PATTERNS, grades_out=None,
):
    """PLAN D6's judge-grading pass, ONE priced dispatch per dispatched cell -> `(grades,
    spent_usd, stopped)`.

    P2-F5 (Phase 2 review): this is the seam that used to be called as `grade_cells(cells)` --
    no spend state in, no spend state out, sitting immediately before `_spend_basis(cells)`. In
    that shape, judge dispatches ran OUTSIDE `would_exceed_ceiling`, judge dollars never entered
    `spend.spent_usd`, and the envelope basis never saw them. Fixed here by taking `spent_usd`/
    `max_usd` IN and returning the updated `spent_usd` OUT: every grade is ceiling-checked with
    `would_exceed_ceiling` (the SAME helper, the SAME re-validation, the candidate loop uses)
    BEFORE `oracle_judge` is called -- never after. A task×candidate cell that was never
    dispatched (already `skipped: cost-ceiling`) has nothing to grade and is recorded skipped
    here too, with the SAME reason -- symmetry with `cells`, one grade slot per cell, no silent
    gaps. Once the ceiling stops grading, it does not un-stop for a smaller remaining cell: a
    stop, once made, holds for the rest of this call, exactly like the candidate loop's `stopped`.

    F4c (Phase 3 review): a task whose reference is EMPTY once test hunks are stripped buys
    nothing but a deanonymised, meaningless grade -- it is recorded `skipped: empty-reference`
    with its note and never dispatched. `grades_out`, when given a list, receives every grade
    record as it is produced: `cmd_run` needs the partial result (and its dollars) when a
    dispatch raises mid-pass, since the return value is lost in that case (F3).
    """
    tasks_by_id = {t["task_id"]: t for t in tasks}
    grades = grades_out if grades_out is not None else []
    stopped = False

    for cell in cells:
        task = tasks_by_id.get(cell["task_id"])
        estimate = estimate_dispatch_usd(judge_model, JUDGE_GRADE_PROFILE, pricing)

        if cell.get("skipped") or task is None:
            grades.append(
                _skipped_grade(
                    cell["task_id"], cell["model"], estimate,
                    reason=cell.get("skipped") or SKIPPED_COST_CEILING,
                )
            )
            continue

        if not _strip_test_hunks(task.get("reference_patch") or "", test_patterns).strip():
            grades.append(
                _skipped_grade(
                    cell["task_id"], cell["model"], estimate,
                    reason=SKIPPED_EMPTY_REFERENCE, note=JUDGE_EMPTY_REFERENCE_NOTE,
                )
            )
            continue

        if not stopped and would_exceed_ceiling(spent_usd, estimate, max_usd):
            stopped = True
        if stopped:
            grades.append(_skipped_grade(cell["task_id"], cell["model"], estimate))
            continue

        grade = oracle_judge(
            task, task["reference_patch"], cell["patch"], judge_model, adapter, runner,
            claude_bin, pricing, slot_seed=slot_seed, candidate_model=cell["model"],
            test_patterns=test_patterns,
        )
        grade = dict(grade)
        grade["task_id"] = cell["task_id"]
        grade["candidate_model"] = cell["model"]
        grade["estimated_usd"] = estimate
        grade["skipped"] = None
        grades.append(grade)
        spent_usd += grade["usd"] or 0.0

    return grades, spent_usd, stopped


# ---------------------------------------------------------------------------------------------
# Oracles (PLAN D5). `solved` comes from oracle (a) ALONE, forever -- an unavailable oracle
# renders `n/a` (never a zero, never False; R6). Oracle (b) is an always-available SIMILARITY
# signal and is never allowed to render without its own not-a-correctness label.

TESTS_NOT_DISCRIMINATING_NOTE = "tests already pass at base — not a discriminating oracle"
STRUCTURAL_LABEL = "similarity signal — NOT a correctness verdict"
STRUCTURAL_NO_REFERENCE_NOTE = (
    "reference patch is empty after stripping test hunks — nothing to compare against, so "
    "similarity is unavailable (n/a), not zero"
)

#: F2 (Phase 3 review). Restoring the base test surface means a candidate CANNOT be `solved`
#: by rewriting a test -- but the attempt itself is signal a verdict reader deserves, so the
#: cell records which test-pattern paths its patch touched. NOT proof of gaming (a genuine fix
#: may legitimately add a regression test); a `solved` earned beside test edits is simply
#: something T8 must be able to see rather than something the envelope hides.
CANDIDATE_TOUCHED_TESTS_NOTE = (
    "candidate patch touches test-pattern path(s) — the grade substrate is CONSTRUCTED from "
    "the task's base state, so nothing the candidate wrote to a test file it was not in scope "
    "to change was ever present when the test command ran"
)

#: F1 (Phase 4 review) -- THE THIRD INSTANCE OF ONE SHAPE, and the last time this kit should
#: have to learn it.
#:
#: Phase 2 protected the ANSWER (`reference_patch`) from the candidate. Phase 3 found the
#: ORACLE (`solved`) was computed from a tree the candidate could write, and restored every
#: path matching `DEFAULT_TEST_PATTERNS`. Phase 4 found that THE TEST HARNESS IS NOT A
#: TEST-PATTERN PATH: `conftest.py`, `run_tests.py`, `Makefile`, `tox.ini`, `pytest.ini`,
#: `setup.py`, `noxfile.py` all read False from `_matches_test_pattern`, so a candidate that
#: touched no module and no test-pattern file and merely rewrote the file `--test-cmd`
#: actually invokes earned `solved` on every cell, cleared the D7 floor, and was APPLIED.
#:
#: Each of those three fixes was a BLACKLIST -- take the candidate's tree and remove the bad
#: parts -- and each was correct for the layer it was aimed at and blind to the next one out,
#: because a blacklist has to correctly ENUMERATE what to take away. The fix here is a
#: WHITELIST, and the difference is the whole point:
#:
#:     THE INVARIANT -- the grade result is a function of
#:         (the task's base state, the candidate's IN-SCOPE patch, the reference test blobs)
#:     and nothing else.
#:
#: The candidate's tree is not graded at all, cleaned or otherwise. `build_grade_substrate`
#: CONSTRUCTS the substrate from those three known-good pieces: a fresh extraction of the
#: base tree (through the read-only `git_target` seam), the candidate's hunks for paths inside
#: the REFERENCE PATCH's scope and no others, then the withheld `test_blobs` last. A harness
#: file, a config file, a dotfile, a planted `sitecustomize.py`, a brand-new file, a symlink,
#: a rename, a `.gitignore`d creation -- none of them has to be anticipated, because none of
#: them is ever applied. There is nothing to enumerate.
#:
#: ("Base state" is base tree PLUS the task's mined `setup_patch` in general mode -- that
#: patch is the injected bug, it is what `prepare_cell_sandbox` hands the candidate, and it is
#: what `capture_patch` baselines against. It is a mining artifact stored in `tasks/<id>.json`
#: and no candidate can write it, so it belongs on the trusted side of the invariant. Omitting
#: it would build a GREEN substrate and mark every general-mode candidate `solved`.)
#:
#: THE TRADEOFF, STATED RATHER THAN HIDDEN. A candidate that legitimately fixes the bug in a
#: file the reference patch did not touch has that work left out of the substrate, and its
#: cell reads `not solved`. That is a FALSE NEGATIVE. It is accepted, and it is made VISIBLE:
#: the cell carries `candidate_modified_out_of_scope` and this note, and the verdict surfaces
#: both, so a reader can see WHY a cell failed rather than being told the model is worse than
#: it is. The asymmetry is the whole argument -- a visible false negative costs a user one
#: investigation; an invisible false positive silently re-routes their real work.
CANDIDATE_OUT_OF_SCOPE_NOTE = (
    "candidate changed file(s) outside the reference patch's scope — the grade substrate is "
    "constructed from the task's base state plus the candidate's IN-SCOPE hunks only, so a "
    "fix that lived only there was never applied and cannot read `solved`: a VISIBLE false "
    "negative, not evidence the candidate did nothing"
)

#: Recording note (read it beside the guarantee above). The out-of-scope PATHS are read off
#: the captured patch, so they are best-effort EVIDENCE -- a `.gitignore`d creation or a pure
#: rename can be missing from this list. The SUBSTRATE guarantee does not depend on it: that
#: is a construction, not an enumeration, and a path missing from this list was excluded from
#: the substrate just the same. Never read a short list as "the candidate stayed in scope".
CANDIDATE_OUT_OF_SCOPE_EVIDENCE_NOTE = (
    "out-of-scope paths are read from the captured patch and are evidence, not a guarantee — "
    "the substrate excludes everything out of scope whether or not the patch names it"
)

#: The degraded twin: no target repo means no base tree, and no base tree means the substrate
#: cannot be CONSTRUCTED at all. There is deliberately no fallback to grading the candidate's
#: own tree -- that fallback is precisely the forgeable grade F1 exists to kill -- so the
#: oracle reports itself unavailable and says why. Absence is not failure (D5/R6) and it is
#: certainly not a pass.
SUBSTRATE_UNAVAILABLE_NOTE = (
    "grade substrate could not be constructed (no target repo supplied) — the tests oracle is "
    "unavailable; the candidate's own tree is never graded as a fallback"
)

#: The other degradation: the in-scope slice of the candidate's patch would not apply to the
#: reconstructed base state (a binary hunk, a patch this module could not parse cleanly). The
#: oracle refuses rather than grading an unpatched substrate, which would read `not solved`
#: for a reason that has nothing to do with the candidate's work.
SUBSTRATE_APPLY_FAILED_NOTE = (
    "the candidate's in-scope patch did not apply to the reconstructed base state — the tests "
    "oracle is unavailable for this cell rather than reporting a failure it did not measure"
)

_DIFF_GIT_HEADER_RE = re.compile(r"^diff --git ")


def _diff_header_path(raw):
    """A `---`/`+++` header's path, `a/`/`b/` prefix stripped -- `None` for `/dev/null`."""
    raw = raw.split("\t")[0].rstrip("\n").strip()
    if raw == "/dev/null" or not raw:
        return None
    for prefix in ("a/", "b/"):
        if raw.startswith(prefix):
            return raw[len(prefix):]
    return raw


def _split_diff_by_file(patch_text):
    """A unified diff -> ordered `[(path, block_text), ...]`, one entry per touched file.

    Stdlib string work only (PLAN D5/T6 -- no external diff lib). Anchored on the `+++ `
    header line, which is present for every file a `git diff` emits (added, modified, or
    deleted -- a deletion's `+++` line is `/dev/null`, and the path is recovered from the
    matching `--- a/<path>` line instead). Works equally on real `git diff` output (which
    leads each file with `diff --git a/X b/X` + an `index` line) and on a hand-built patch
    that starts straight at `--- a/X` -- the `diff --git` line is optional context, never
    required to resolve a path.
    """
    blocks = []
    preamble = []
    current_path = None
    current_lines = []

    def flush():
        if current_path is not None:
            blocks.append((current_path, "".join(current_lines)))

    for line in (patch_text or "").splitlines(keepends=True):
        if _DIFF_GIT_HEADER_RE.match(line):
            flush()
            current_path, current_lines = None, []
            preamble = [line]
            continue
        if line.startswith("--- ") and current_path is not None:
            # A `---` line while we are still inside a PRIOR file's body (no `diff --git`
            # line ever separated them -- a hand-built patch, or minimal `---`/`+++`-only
            # output) always starts the NEXT file's header.
            flush()
            current_path, current_lines = None, []
            preamble = [line]
            continue
        if line.startswith("+++ "):
            path = _diff_header_path(line[4:])
            if path is None:
                for prior in reversed(preamble):
                    if prior.startswith("--- "):
                        path = _diff_header_path(prior[4:])
                        break
            flush()
            current_path = path
            current_lines = preamble + [line]
            preamble = []
            continue
        if current_path is None:
            preamble.append(line)
        else:
            current_lines.append(line)
    flush()
    return blocks


def _strip_test_hunks(patch_text, test_patterns=DEFAULT_TEST_PATTERNS):
    """Drop every file-block whose path matches `test_patterns` from a unified diff.

    P1-F5 + Nit (Phase 1/2 reviews, carried into T6): an issue-replay `reference_patch` is
    the FULL `git diff base..fix`, so it carries the fix commit's own test hunks -- files a
    candidate structurally cannot produce, because those exact blobs are deliberately
    withheld from its sandbox (THE LEAK RULE). Comparing an unstripped reference against a
    candidate patch that correctly fixes the source and touches no tests would systematically
    DEPRESS its similarity score. This strip lives at the GRADING/SIZING boundary -- it never
    touches `reference_patch` as mined or stored (T2's job, untouched here); it is applied
    fresh, in memory, wherever a reference patch is being compared or sized.
    """
    blocks = _split_diff_by_file(patch_text)
    kept = [
        text for path, text in blocks
        if not _matches_test_pattern(path, test_patterns)
    ]
    return "".join(kept)


def _diff_signature(patch_text):
    """A patch's structural fingerprint: `(files touched, changed content-lines, LOC)`.

    `changed content-lines` is `{(path, line)}` over every `+`/`-` line (header lines
    `+++`/`---` excluded) -- two patches share an entry only when the SAME file changed the
    SAME line the SAME way, which is what makes `hunk_overlap` mean something beyond
    "touched the same files".
    """
    files = set()
    lines = set()
    loc = 0
    for path, text in _split_diff_by_file(patch_text):
        if not path:
            continue
        files.add(path)
        for line in text.splitlines():
            if line.startswith("+++") or line.startswith("---"):
                continue
            if line.startswith("+") or line.startswith("-"):
                lines.add((path, line))
                loc += 1
    return files, lines, loc


def oracle_structural(reference_patch, candidate_patch, test_patterns=DEFAULT_TEST_PATTERNS):
    """Oracle (b) -- PLAN D5's SIMILARITY signal, never a correctness verdict.

    `reference_patch` is stripped of test-pattern file-blocks BEFORE comparison (P1-F5 + Nit
    above) -- `candidate_patch` is compared as-is, since a candidate touching a test file the
    reference never withheld is itself signal (`out_of_scope_files`). An empty candidate
    patch (a candidate that produced no change at all) short-circuits to all-zero metrics --
    there is nothing to jaccard against nothing.

    F4b (Phase 3 review) -- THE `available` CHANNEL. D5 calls this oracle "always available",
    and that was read as "always emits numbers". It is not the same claim: when the stripped
    reference parses to NOTHING (a tests-only fix commit, a binary-only change, a diff this
    module could not parse) there is no reference to be similar TO, and the old code answered
    `files_jaccard: 0.0` for a perfectly correct candidate while counting its one real file as
    out of scope -- a made-up zero where D5/R6 demand `n/a`. Unavailable results carry `None`
    in every metric slot, never a number a renderer could print as 0.00.

    The `label` key is REQUIRED on every result -- a test asserts it verbatim.
    """
    stripped_reference = _strip_test_hunks(reference_patch or "", test_patterns)
    if not stripped_reference.strip():
        return {
            "oracle": "structural",
            "available": False,
            "files_jaccard": None,
            "hunk_overlap": None,
            "loc_delta_ratio": None,
            "out_of_scope_files": None,
            "label": STRUCTURAL_LABEL,
            "notes": STRUCTURAL_NO_REFERENCE_NOTE,
        }

    # Nit (Phase 3 review): `if not candidate_patch` missed a whitespace-only patch, which is
    # the same event -- the candidate produced no change -- reported without its note.
    if not (candidate_patch or "").strip():
        return {
            "oracle": "structural",
            "available": True,
            "files_jaccard": 0.0,
            "hunk_overlap": 0.0,
            "loc_delta_ratio": 0.0,
            "out_of_scope_files": 0,
            "label": STRUCTURAL_LABEL,
            "notes": "candidate produced no change",
        }

    ref_files, ref_lines, ref_loc = _diff_signature(stripped_reference)
    cand_files, cand_lines, cand_loc = _diff_signature(candidate_patch)

    files_union = ref_files | cand_files
    files_jaccard = (len(ref_files & cand_files) / len(files_union)) if files_union else 0.0

    lines_union = ref_lines | cand_lines
    hunk_overlap = (len(ref_lines & cand_lines) / len(lines_union)) if lines_union else 0.0

    # Nit (Phase 3 review): `ref_loc == 0 and cand_loc == 0` used to read 1.0 -- PERFECT
    # agreement out of two patches this module parsed no changed lines from at all. Zero
    # parsed data is not agreement; it is no signal.
    if ref_loc == 0 and cand_loc == 0:
        loc_delta_ratio = 0.0
    else:
        loc_delta_ratio = min(ref_loc, cand_loc) / max(ref_loc, cand_loc)

    out_of_scope_files = len(cand_files - ref_files)

    return {
        "oracle": "structural",
        "available": True,
        "files_jaccard": files_jaccard,
        "hunk_overlap": hunk_overlap,
        "loc_delta_ratio": loc_delta_ratio,
        "out_of_scope_files": out_of_scope_files,
        "label": STRUCTURAL_LABEL,
        "notes": "",
    }


def _reference_scope_paths(reference_patch):
    """Every path the REFERENCE patch touches -> THE WHITELIST (F1).

    This is the only thing that decides what a candidate is allowed to have applied to the
    grade substrate. Read straight off the diff's own header lines (`--- a/X`, `+++ b/X`, and
    git's `rename from`/`rename to`) rather than through `_split_diff_by_file`, so BOTH sides
    of a rename and both sides of a delete/add land in scope. Being generous here is the
    false-negative-reducing direction and costs nothing in forgery terms: every path admitted
    comes from an artifact mined out of the target's history, which no candidate can write.

    Note what is NOT stripped: the reference's own test hunks stay in scope. A file the FIX
    commit touched is legitimately in play for the candidate too -- and the `test_blobs`,
    written LAST into the substrate, are what keep those from being forgeable.
    """
    paths = set()
    for line in (reference_patch or "").splitlines():
        if line.startswith("--- ") or line.startswith("+++ "):
            path = _diff_header_path(line[4:])
            if path:
                paths.add(path)
        elif line.startswith("rename from ") or line.startswith("rename to "):
            path = line.split(" ", 2)[2].strip()
            if path:
                paths.add(path)
    return paths


def _split_patch_by_scope(candidate_patch, scope):
    """A candidate patch -> `(in_scope_diff_text, out_of_scope_paths)`.

    The first return value is the ONLY part of the candidate's work that reaches the substrate;
    the second is EVIDENCE for the verdict and reaches nothing. Keeping the two apart in one
    function is deliberate: the guarantee must not be able to drift away from what gets
    reported beside it.
    """
    in_scope, out_of_scope = [], []
    for path, text in _split_diff_by_file(candidate_patch or ""):
        if path and path in scope:
            in_scope.append(text)
        elif path:
            out_of_scope.append(path)
    return "".join(in_scope), sorted(set(out_of_scope))


def build_grade_substrate(task, candidate_patch, dest, target_repo, git_runner=None,
                          templates=None):
    """F1's whitelist: CONSTRUCT the tree oracle (a) grades, from three trusted pieces.

        the grade result is a function of
            (the task's base state, the candidate's IN-SCOPE patch, the reference test blobs)
        and nothing else.

    In order, and the order is load-bearing:

      1. **The task's base state**, built by `prepare_cell_sandbox` -- the SAME function that
         builds the candidate's own sandbox, so the two cannot drift. That is a history-free
         extraction of `base_commit` through the read-only `git_target` seam, plus the task's
         mined `setup_patch` in general mode (the injected bug: omit it and the substrate is
         green and every candidate is `solved`), plus -- when a `--setup-cmd` template is in
         play (T17) -- that template's prepared SETUP ARTIFACTS. Nothing here is
         candidate-writable: no candidate tree, patch or sandbox path is an input to preparing a
         template, the captured artifacts are held outside the run dir (so no candidate's `../`
         reaches them), and every artifact is re-verified against its capture-time content hash
         before it is overlaid (T17R/F1).
      2. **The candidate's IN-SCOPE hunks**, and only those -- `git apply` of the slice of its
         captured patch whose paths are in `_reference_scope_paths`. Everything else it wrote
         is simply not applied. No harness file, config file, dotfile, planted
         `sitecustomize.py`, new file, symlink or `.gitignore`d creation has to be
         anticipated, because the substrate is built by ADDING known-good pieces rather than
         by subtracting anticipated bad ones.
      3. **The reference `test_blobs`**, written last so they win over anything in (2) that
         touched the same path.

    The patch file itself is written to a system temp dir and unlinked the moment `git apply`
    returns -- never under the run dir, exactly as `prepare_cell_sandbox` does it, and for the
    same reason (a candidate's cwd is one `../` away from the run dir's working area).

    Returns `{"path", "in_scope_applied", "out_of_scope", "notes"}`. `in_scope_applied` is
    False only when `git apply` refused the slice; the caller must then decline to grade
    rather than report a failure it did not measure (`SUBSTRATE_APPLY_FAILED_NOTE`).

    ONE RESIDUAL, STATED. An in-scope path that is a test file with no extracted blob (the fix
    commit touched it, but mining could not read it -- a deleted or non-UTF-8 test file, both
    already noted at mining time) keeps the candidate's hunks. It is in scope by the
    reference's own account, so this is the whitelist behaving as defined rather than a hole in
    it; re-narrowing it by NAME is exactly the move this fix exists to stop.
    """
    info, _baseline = prepare_cell_sandbox(
        task, target_repo, dest, git_runner=git_runner, templates=templates
    )
    substrate = Path(info["path"])
    notes = []

    scope = _reference_scope_paths(task.get("reference_patch"))
    in_scope_diff, out_of_scope = _split_patch_by_scope(candidate_patch, scope)

    applied = True
    if in_scope_diff.strip():
        with tempfile.TemporaryDirectory(prefix="repo-bench-inscope-") as holder:
            patch_file = Path(holder) / "in-scope.patch"
            patch_file.write_text(in_scope_diff)
            rc, out = git_sandbox(substrate, "apply", str(patch_file), git_runner=git_runner)
            patch_file.unlink()
        if rc != 0:
            applied = False
            notes.append(f"{SUBSTRATE_APPLY_FAILED_NOTE}: {(out or '').strip()}")

    if applied:
        for rel_path, blob in (task.get("test_blobs") or {}).items():
            target = substrate / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(blob)

    return {
        "path": str(substrate),
        "in_scope_applied": applied,
        "out_of_scope": out_of_scope,
        "notes": notes,
    }


def oracle_tests(
    task, candidate_patch, test_cmd, test_runner, scratch_dir, target_repo=None,
    git_runner=None, test_patterns=DEFAULT_TEST_PATTERNS, templates=None,
):
    """Oracle (a) -- PLAN D5's objective backbone. `solved` can ONLY ever come from here.

    THE CANDIDATE'S TREE IS NOT AN INPUT. That is why the second parameter is its captured
    PATCH and not its sandbox path: the substrate this grades is CONSTRUCTED by
    `build_grade_substrate` from the task's base state, the in-scope slice of that patch, and
    the withheld `test_blobs` -- see `CANDIDATE_OUT_OF_SCOPE_NOTE` for the invariant, the three
    blacklists that failed before it, and the false negative it deliberately accepts. The
    substrate is a throwaway under `scratch_dir` (PLAN D3/D11 -- never a system temp dir), gone
    before this returns, and the candidate's own sandbox is never read, copied or written here.

    THE LEAK RULE is unchanged and is now easier to see: `test_blobs` encode the fix, and they
    are written into the constructed substrate only -- never into the sandbox the candidate
    worked in.

    Unavailable -- never a failing grade, because absence is not failure (D5/R6) and is
    certainly not a pass:
      * no `test_cmd` supplied;
      * an issue-replay task whose fix touched no tests (`oracle_tests_available` False);
      * no target repo, so the substrate cannot be constructed at all (direct unit calls only
        -- `cmd_run` always passes one). There is NO fallback to grading the candidate's tree;
        that fallback is the forgeable grade F1 exists to kill.
      * a `--setup-cmd` grade template that would not prepare (T17). A toolchain that does not
        build is ABSENCE -- rendering it as `passed: False` would mark every candidate wrong
        and produce a confident, entirely fictional verdict.
      * a `--setup-cmd` template whose captured artifacts no longer match their capture-time
        content hashes (T17R). Bytes that changed after capture are bytes nobody may grade
        from; the substrate is not built at all, and `passed` stays None.
      * the in-scope slice would not apply to the reconstructed base state.
    `passed` stays `None` in every one of those cases, never `False`. `out_of_scope` stays
    `None` when no substrate was built -- `[]` would claim "measured, nothing out of scope".
    """
    if not test_cmd:
        return {
            "oracle": "tests", "available": False, "passed": None, "rc": None,
            "notes": "no --test-cmd supplied -- tests oracle unavailable",
            "out_of_scope": None,
        }
    if task["mode"] == "issue-replay" and not task.get("oracle_tests_available"):
        return {
            "oracle": "tests", "available": False, "passed": None, "rc": None,
            "notes": "issue-replay task's fix touched no tests -- tests oracle unavailable",
            "out_of_scope": None,
        }
    if target_repo is None or not task.get("base_commit"):
        return {
            "oracle": "tests", "available": False, "passed": None, "rc": None,
            "notes": SUBSTRATE_UNAVAILABLE_NOTE,
            "out_of_scope": None,
        }
    # T17: checked BEFORE any substrate is built, and BEFORE `--test-cmd` is ever invoked --
    # running the suite in a tree whose dependencies were never installed reports a `not solved`
    # that measures the toolchain, not the model.
    if templates is not None:
        record = templates.prepare(task)
        if not record["ok"]:
            return {
                "oracle": "tests", "available": False, "passed": None, "rc": None,
                "notes": f"{SETUP_FAILED_NOTE} (exit {record['rc']})",
                "out_of_scope": None,
            }
        # T17R/F1: the second, independent mechanism. The store lives outside the run dir, and
        # its bytes are checked anyway -- a store that changed between capture and overlay is a
        # measurement that did not happen, not a candidate that failed.
        tampered = templates.verify(record)
        if tampered:
            return {
                "oracle": "tests", "available": False, "passed": None, "rc": None,
                "notes": f"{ARTIFACT_TAMPERED_NOTE} ({', '.join(tampered)})",
                "out_of_scope": None,
            }

    runner = test_runner or default_test_runner
    scratch_dir = Path(scratch_dir)
    scratch_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="repo-bench-grade-", dir=str(scratch_dir)) as tmp:
        built = build_grade_substrate(
            task, candidate_patch, Path(tmp) / "substrate", target_repo, git_runner=git_runner,
            templates=templates,
        )
        if not built["in_scope_applied"]:
            return {
                "oracle": "tests", "available": False, "passed": None, "rc": None,
                "notes": "; ".join(built["notes"]),
                "out_of_scope": built["out_of_scope"],
            }
        rc, _output = runner(test_cmd, built["path"])

    notes = list(built["notes"])
    if built["out_of_scope"]:
        notes.append(
            f"{CANDIDATE_OUT_OF_SCOPE_NOTE} ({', '.join(built['out_of_scope'])}); "
            f"{CANDIDATE_OUT_OF_SCOPE_EVIDENCE_NOTE}"
        )
    if rc != 0:
        notes.append("test command failed in the constructed grade substrate")
    return {
        "oracle": "tests", "available": True, "passed": (rc == 0), "rc": rc,
        "notes": "; ".join(notes),
        # F1: `[]` (measured, nothing out of scope) and `None` (no substrate was built) are
        # different facts and stay different -- absence is never rendered as a clean result.
        "out_of_scope": built["out_of_scope"],
    }


def oracle_tests_red_check(task, target_repo, test_cmd, test_runner, scratch_dir, git_runner=None,
                           templates=None):
    """Red-check at base (PLAN D5/T6 item 2) -- issue-replay only, meant to run ONCE per task
    per run (the caller, `cmd_run`, caches the result across that task's candidates).

    A CLEAN sandbox off `task["base_commit"]` (issue-replay's base IS the pre-fix state, so
    there is no `setup_patch` to apply here -- general-mode tasks were already red-validated
    at mining time and never reach this function) with the fix commit's withheld test blobs
    written in, then `test_cmd` run against it. If it PASSES, the blobs cannot discriminate a
    correct candidate from a buggy one for this task -- the caller must demote that task's
    oracle to `available: False` with `TESTS_NOT_DISCRIMINATING_NOTE` rather than let a
    non-discriminating pass inflate objective coverage (R6).

    Returns `None` when red-checking does not apply at all (no `test_cmd`, general mode, no
    test blobs to check, or -- T17/T17R -- a `--setup-cmd` template that would not prepare or
    whose artifacts fail content verification) -- the
    caller passes that straight through as "nothing to demote". Demoting a task on the strength
    of a suite that could not run is a second lie on top of the first, and the cell's own tests
    oracle already reports the setup failure. Otherwise
    `{"checked": True, "passed_at_base": bool}`. The throwaway sandbox lives under
    `scratch_dir` (PLAN D3/D11) and is gone before this function returns, win or lose.
    """
    if not test_cmd or task["mode"] != "issue-replay" or not task.get("oracle_tests_available"):
        return None
    if templates is not None:
        record = templates.prepare(task)
        if not record["ok"] or templates.verify(record):
            return None

    runner = test_runner or default_test_runner
    scratch_dir = Path(scratch_dir)
    scratch_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="repo-bench-redcheck-", dir=str(scratch_dir)) as tmp:
        info = make_sandbox(target_repo, task["base_commit"], Path(tmp) / "base", git_runner=git_runner)
        base_path = Path(info["path"])
        if templates is not None:
            templates.overlay(task, base_path)
        for rel_path, blob in (task.get("test_blobs") or {}).items():
            target = base_path / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(blob)
        rc, _output = runner(test_cmd, str(base_path))

    return {"checked": True, "passed_at_base": (rc == 0)}


def _touched_test_paths(patch_text, test_patterns=DEFAULT_TEST_PATTERNS):
    """Test-pattern paths a candidate's captured patch touches (F2) -> sorted list."""
    return sorted({
        path for path, _text in _split_diff_by_file(patch_text or "")
        if path and _matches_test_pattern(path, test_patterns)
    })


def _skipped_cell(task_id, model_id, estimated_usd, reason=SKIPPED_COST_CEILING):
    """A cell that was never dispatched. Same key set as a dispatched cell, all-None where a
    dispatch would have put data -- an unmeasured cell renders as absence, never as a zero."""
    return {
        "task_id": task_id,
        "model": model_id,
        "wall_seconds": None,
        "usage": None,
        "usd": None,
        "usd_basis": None,
        "patch": None,
        "dispatch_rc": None,
        "estimated_usd": estimated_usd,
        "skipped": reason,
        "oracles": None,
        # F2: key parity with a dispatched cell -- a cell with no patch touched no test path,
        # and `None` (absence) says that without claiming a measured empty list.
        "candidate_touched_tests": None,
        # F1: same rule -- a cell that was never dispatched was never swept, and `None` says
        # "not measured" where `[]` would claim "measured, nothing out of scope".
        "candidate_modified_out_of_scope": None,
    }


def _spend_basis(cells, grades=()):
    """PLAN D1's `spend basis`, derived from what the cells AND grades actually recorded --
    never asserted.

    P2-F5: the basis used to be derived from candidate cells alone, which read the envelope as
    `actual` even on a run whose judge dollars were all estimates (or vice versa). `grades`
    defaults to `()` so every existing caller that only ever priced cells keeps working
    unchanged. No dispatched cell or grade at all means nothing was spent and nothing was
    measured: the only honest label left is `estimated` (the numbers in the envelope are plan
    estimates).
    """
    bases = {
        r["usd_basis"] for r in (*cells, *grades) if not r.get("skipped") and r.get("usd_basis")
    }
    if not bases:
        return "estimated"
    if len(bases) == 1:
        return bases.pop()
    return "mixed"


# ---------------------------------------------------------------------------------------------
# `verdict` (PLAN D5/D7/D10) -- where all four oracles finally meet, and the last place the
# discipline every layer above was built for can be lost.
#
# THERE IS NO COMPOSITE SCORE IN THIS SECTION. No weighted sum, no normalised blend, no
# "overall". `solved` is oracle (a) and nothing else, forever (R6): the capability order is a
# single-oracle rate with its COUNTS printed beside it, the judge may ORDER A TIE and is
# annotated `tiebreak: judge (subjective)` whenever it does, and similarity orders nothing at
# all. An oracle that was unavailable renders `n/a` -- never 0.00, never a dropped row. Below
# the evidence floor the card says so loudly, in every rendering, and still prints the raw
# measurement table: refusing a routing-grade CLAIM is not the same as hiding the data.

VERDICT_SCHEMA_VERSION = 1

#: What an unavailable oracle renders as, everywhere. Grep-able on purpose (PLAN D5: "the
#: verdict table prints one column per oracle with explicit n/a cells").
NA = "n/a"

VERDICT_GOALS = ("tiers", "daily-driver", "both")

#: The tier map's slots, best-first, and the loop-engineering roles they gloss to (PLAN
#: D5/T8). A gloss, never a promise: `≈` is doing real work in that string.
TIER_SLOTS = ("strong", "mid", "weak")
TIER_ROLE_GLOSS = "strong≈reviewer, mid≈implementer, weak≈verifier"

#: The daily-driver rule's two dials (PLAN D5/T8 item 1.iii), pinned as structural constants:
#: which task sizes count as "quick task resolution", and how many tasks behind the best a
#: candidate may be and still count as capability-equivalent for the cost comparison.
DAILY_DRIVER_PROFILES = ("XS", "S")
DAILY_DRIVER_SLACK = 1

#: The one sentence that governs every column in the card. Rides as a LABEL on every verdict,
#: below floor or not -- the vocabulary is load-bearing (GUARDRAILS).
SOLVED_SOURCE_LABEL = (
    "`solved` = the tests oracle (a) passed, and nothing else — a judge grade or a similarity "
    "score never contributes to it, in any column, ever (PLAN D5/R6)"
)

#: PLAN D10's three legs, and the two honest absences.
NO_PUBLISHED_ENTRY = "no published entry"
NO_LEDGER_EVIDENCE = "no ledger evidence"
DISAGREEMENT_PREFIX = "DISAGREEMENT — signal, not error"
THREE_LEGS_LABEL = (
    "the three legs (published prior / observed ledger / this run's measurement) stand side "
    "by side and are NEVER merged into one number (PLAN D10)"
)

#: The judge grading pass runs AFTER the whole candidate loop, so a run that meets its ceiling
#: consumes it candidate-first and drops 100% of the judge grades rather than a proportional
#: slice. A verdict whose judge column is empty for that reason must say so rather than read
#: as "the judge had nothing to say".
JUDGE_BUDGET_STARVED_LABEL = (
    "judge column EMPTY by budget, not by silence — judge grading is a post-loop pass, so a "
    "run that hits its --max-usd ceiling spends it candidate-first and drops 100% of the "
    "grades rather than a proportional slice"
)

#: F2/T7R, carried into T8: a `solved` earned alongside test-file edits is not proof of gaming
#: (the test surface is restored from base before grading, so the edit cannot have earned it) --
#: but it is exactly the thing a verdict must not bury.
SOLVED_WITH_TEST_EDITS_LABEL = (
    "at least one `solved` cell came from a candidate whose patch ALSO touched test-pattern "
    "path(s) — the test surface is restored from base before grading, so the edit did not earn "
    "the pass, and the fact is surfaced here rather than buried (see the touched-tests column)"
)

NO_PROFILE_DATA_NOTE = (
    "task size profiles are unavailable in this run dir (plan.json and tasks/*.json are both "
    "missing or unreadable) — the daily-driver rule was applied over ALL tasks instead of the "
    f"{'/'.join(DAILY_DRIVER_PROFILES)} subset, and that widening is part of its printed rule"
)


def default_benchmarks_path():
    """The PUBLISHED leg's data file -- `bench_routing.DEFAULT_BENCHMARKS_PATH`, REUSED.

    `data/benchmarks.aa.json`'s location belongs to `bench_routing` exactly as
    `data/pricing.json`'s belongs to `cost_report`: this module re-derives NEITHER path
    (PLAN D10/R4). Injectable at every call site so a test can point the join at a synthetic
    fixture instead.
    """
    return Path(_br().DEFAULT_BENCHMARKS_PATH)


def _below_floor_label(min_tasks):
    """PLAN D7's stamp, verbatim. One function so the card, the envelope and verdict.md can
    never carry three slightly different wordings of the same refusal."""
    return (
        f"BELOW EVIDENCE FLOOR — not a routing-grade verdict (need >= {min_tasks} "
        f"objectively-scored tasks per candidate)"
    )


def resolve_min_tasks(flag_value):
    """PLAN D7: `max(MIN_EVIDENCE_TASKS, --min-tasks)` -- the flag can only RAISE the floor.

    A `--min-tasks 3` against a floor of 5 is not an error and not a refusal; it simply does
    nothing, because a per-run flag that could lower a structural floor is not a floor. Kept
    as its own named function so no caller ever re-derives the `max()` in the other direction.
    """
    if flag_value is None:
        return MIN_EVIDENCE_TASKS
    return max(MIN_EVIDENCE_TASKS, int(flag_value))


def _median(values):
    """Median of the non-None values, or None when there are none. NEVER 0.0 on empty input --
    a median of nothing is absence, and absence renders `n/a`."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    if len(vals) % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


def _fmt_num(value, spec=".2f", na=NA):
    """A number in its format, or `n/a`. THE renderer-level guard against the failure this
    task is most likely to hit: a `None` printed as `0.00` is a measurement claim nobody made."""
    return na if value is None else format(value, spec)


def _expand_oracles(cell, grade):
    """One results.json cell (+ its joined judge grade) -> all FOUR oracle readings, explicit.

    THE FOUR TRAPS in the inherited cell shape, disarmed here, once, so no renderer or
    aggregator below has to remember them (Phase 3 review, carried into T8):

      1. A SKIPPED cell collapses all four oracles into ONE `"oracles": None` sentinel. That
         expands into four labelled `n/a`s here -- never one blank row, never a dropped row.
      2. The judge grade is NOT under `oracles`: it lives in a SIBLING top-level `grades` list
         joined on `(task_id, candidate_model)`. An ABSENT grade is synthesized as `n/a`
         rather than skipped, and its two skip reasons are kept apart -- `cost-ceiling` is a
         budget casualty, `empty-reference` is not (it is a deliberate refusal to buy a
         deanonymised grade) and counting them together would misattribute a design decision
         to the budget.
      3. Oracle (d) is bare cell scalars (`wall_seconds` / `usd` / `usd_basis`) OUTSIDE
         `oracles`, and their `None`s are precisely the kind a renderer prints as `0.00`.
      4. A demoted tests record carries `rc: None` beside `passed: null`. `rc` is never read
         as a signal -- here or anywhere: `available` and `passed` are the whole vocabulary.
    """
    oracles = cell.get("oracles")
    tests_raw = (oracles or {}).get("tests") or {}
    structural_raw = (oracles or {}).get("structural") or {}

    tests_available = bool(tests_raw.get("available"))
    # `solved` is this AND: an unavailable oracle can never be `solved`, and `passed` is only
    # ever True/None -- never False-by-absence (D5/R6).
    solved = bool(tests_available and tests_raw.get("passed") is True)
    tests = {
        "available": tests_available,
        "solved": solved if tests_available else None,
        "notes": tests_raw.get("notes") or "",
    }

    structural_available = bool(structural_raw.get("available"))
    structural = {
        "available": structural_available,
        "files_jaccard": structural_raw.get("files_jaccard") if structural_available else None,
        "hunk_overlap": structural_raw.get("hunk_overlap") if structural_available else None,
        "loc_delta_ratio": (
            structural_raw.get("loc_delta_ratio") if structural_available else None
        ),
        "out_of_scope_files": (
            structural_raw.get("out_of_scope_files") if structural_available else None
        ),
        "label": STRUCTURAL_LABEL,
        "notes": structural_raw.get("notes") or "",
    }

    judge = {
        "grade": None,
        "equivalent": None,
        "status": "no grade record",
        "skipped": None,
        "label": JUDGE_LABEL,
    }
    if grade is not None:
        judge["skipped"] = grade.get("skipped")
        parsed = grade.get("grade")
        if grade.get("skipped"):
            judge["status"] = f"skipped: {grade['skipped']}"
        elif parsed:
            judge["grade"] = parsed.get("candidate_grade")
            judge["equivalent"] = parsed.get("equivalent")
            judge["status"] = parsed.get("candidate_grade") or "unparseable"
        else:
            judge["status"] = "unparseable"

    return {
        "task_id": cell.get("task_id"),
        "candidate": cell.get("model"),
        "skipped": cell.get("skipped"),
        "tests": tests,
        "structural": structural,
        "judge": judge,
        # Oracle (d): read straight off the cell, `None`s preserved as `None`.
        "cost": {"usd": cell.get("usd"), "usd_basis": cell.get("usd_basis")},
        "latency": {"wall_seconds": cell.get("wall_seconds")},
        "candidate_touched_tests": cell.get("candidate_touched_tests"),
        # F1 (Phase 4 review): the out-of-scope sweep's record. A pre-F1 envelope has no such
        # key at all, and `None` -- "no sweep is recorded for this cell" -- is the honest
        # reading of that, exactly as it is for a skipped cell.
        "candidate_modified_out_of_scope": cell.get("candidate_modified_out_of_scope"),
    }


def _grades_index(results):
    """The sibling `grades` list, keyed `(task_id, candidate_model)` -- trap 2's join."""
    index = {}
    for grade in results.get("grades") or []:
        index[(grade.get("task_id"), grade.get("candidate_model"))] = grade
    return index


def _task_size_profiles(run_dir):
    """`task_id -> size_profile` from the run dir's OWN records -> (profiles, notes).

    results.json cells do not carry a size profile, so the daily-driver rule (which is scoped
    to the XS/S subset) reads it from `plan.json`'s task summaries, falling back to
    `tasks/<id>.json`. Both can legitimately be missing -- `STORE_WRITE_FAILED_LABEL` is
    exactly that run -- in which case this returns what it has plus a note, and the caller
    widens the rule and SAYS SO rather than silently scoring a different task set.
    """
    run_dir = Path(run_dir)
    profiles, notes = {}, []
    plan_path = run_dir / "plan.json"
    if plan_path.exists():
        try:
            plan = json.loads(plan_path.read_text())
            for row in plan.get("tasks") or []:
                if row.get("task_id") and row.get("size_profile"):
                    profiles[row["task_id"]] = row["size_profile"]
        except (json.JSONDecodeError, UnicodeDecodeError, OSError, AttributeError) as e:
            notes.append(f"plan.json unreadable ({e}) — size profiles fell back to tasks/")
    for path in sorted((run_dir / "tasks").glob("*.json")) if (run_dir / "tasks").is_dir() else []:
        try:
            task = json.loads(path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
            notes.append(f"task record {path.name} unreadable ({e}) — its size profile is absent")
            continue
        if isinstance(task, dict) and task.get("task_id") and task.get("size_profile"):
            profiles.setdefault(task["task_id"], task["size_profile"])
    return profiles, notes


def _candidate_summary(candidate, rows):
    """Per-candidate aggregate over its expanded rows. Every axis stays in its own class.

    `objective_n` counts cells whose TESTS oracle was available; `solved_n` counts oracle-(a)
    passes among them and has no other source. The judge distribution and the structural
    medians sit beside those counts, labelled, and are never folded into them.
    """
    dispatched = [r for r in rows if not r["skipped"]]
    objective = [r for r in rows if r["tests"]["available"]]
    solved_rows = [r for r in objective if r["tests"]["solved"]]
    priced_usd = [r["cost"]["usd"] for r in dispatched if r["cost"]["usd"] is not None]

    judge_counts = {"correct": 0, "partial": 0, "incorrect": 0}
    judge_unparseable = 0
    judge_skipped_ceiling = 0
    judge_skipped_empty_reference = 0
    judge_absent = 0
    for r in rows:
        status = r["judge"]["status"]
        if status in judge_counts:
            judge_counts[status] += 1
        elif status == "unparseable":
            judge_unparseable += 1
        elif r["judge"]["skipped"] == SKIPPED_COST_CEILING:
            judge_skipped_ceiling += 1
        elif r["judge"]["skipped"] == SKIPPED_EMPTY_REFERENCE:
            judge_skipped_empty_reference += 1
        else:
            judge_absent += 1

    objective_n = len(objective)
    solved_n = len(solved_rows)
    solved_with_test_edits = sorted(
        r["task_id"] for r in solved_rows if r["candidate_touched_tests"]
    )
    # F1: the false-negative population, named. These are objectively-scored cells that read
    # `not solved` AND had work reverted from outside the reference patch's scope -- the exact
    # shape where "the model failed" and "we reverted the model's fix" are indistinguishable
    # from the number alone. Never subtracted from anything: it is a caveat on a count, not a
    # correction to it, and quietly adjusting `solved_n` would be the blend R6 forbids.
    not_solved_with_out_of_scope = sorted(
        r["task_id"] for r in objective
        if not r["tests"]["solved"] and r["candidate_modified_out_of_scope"]
    )

    return {
        "candidate": candidate,
        "cells_n": len(rows),
        "dispatched_n": len(dispatched),
        "skipped_n": len(rows) - len(dispatched),
        "skipped_reasons": sorted({r["skipped"] for r in rows if r["skipped"]}),
        # Oracle (a) -- the ONLY source of `solved`.
        "objective_n": objective_n,
        "solved_n": solved_n,
        "solved_rate": (solved_n / objective_n) if objective_n else None,
        "solved_task_ids": sorted(r["task_id"] for r in solved_rows),
        "solved_with_test_edits": solved_with_test_edits,
        "touched_tests_n": sum(1 for r in rows if r["candidate_touched_tests"]),
        "not_solved_with_out_of_scope": not_solved_with_out_of_scope,
        "out_of_scope_n": sum(1 for r in rows if r["candidate_modified_out_of_scope"]),
        # Oracle (c) -- subjective, labelled, never part of `solved`.
        "judge": {
            **judge_counts,
            "unparseable": judge_unparseable,
            "skipped_cost_ceiling": judge_skipped_ceiling,
            "skipped_empty_reference": judge_skipped_empty_reference,
            "no_grade_record": judge_absent,
            "na": (
                judge_unparseable + judge_skipped_ceiling
                + judge_skipped_empty_reference + judge_absent
            ),
            "label": JUDGE_LABEL,
        },
        # Oracle (b) -- similarity, medians only, always with its label.
        "structural_medians": {
            "files_jaccard": _median([r["structural"]["files_jaccard"] for r in rows]),
            "hunk_overlap": _median([r["structural"]["hunk_overlap"] for r in rows]),
            "loc_delta_ratio": _median([r["structural"]["loc_delta_ratio"] for r in rows]),
            "available_n": sum(1 for r in rows if r["structural"]["available"]),
            "label": STRUCTURAL_LABEL,
        },
        # Oracle (d) -- dollars carry their basis, latency is a median, both `None` on absence.
        # A dispatched cell with NO priced dollars is counted as unpriced, never summed as 0.
        "cost": {
            "usd_total": (
                sum(priced_usd) if priced_usd else None
            ),
            "usd_unpriced_n": len(dispatched) - len(priced_usd),
            "usd_median": _median([r["cost"]["usd"] for r in dispatched]),
            "basis": _spend_basis(
                [{"usd_basis": r["cost"]["usd_basis"], "skipped": r["skipped"]} for r in rows]
            ),
        },
        "latency": {
            "wall_seconds_median": _median([r["latency"]["wall_seconds"] for r in dispatched]),
        },
    }


def _capability_order(summaries):
    """THE RULE, step (i)+(ii): order candidates by oracle (a), tie-break explicitly.

    Primary key: `solved_n / objective_n`. A candidate with NO objectively-scored cell has no
    capability reading at all and sorts last -- it is not a zero (R6), it is an absence, and
    the card says which. Ties are broken by the judge's `correct` count and ANNOTATED
    `tiebreak: judge (subjective)`; any remaining tie is broken by candidate id and annotated
    too. A subjective signal may ORDER A TIE; it may never create one, and it never touches
    the primary key.
    """
    # Two passes, not one composite key: sort ascending by candidate id first, then re-sort
    # (stably) on the descending capability keys. The stable sort is what makes the final
    # tie-break "candidate id, ascending" without an id-comparison trick that would order
    # `x` after `xy`.
    ordered = sorted(summaries, key=lambda s: s["candidate"])
    ordered.sort(
        key=lambda s: (
            0 if s["solved_rate"] is None else 1,   # no reading at all sorts last
            s["solved_rate"] if s["solved_rate"] is not None else 0.0,
            s["solved_n"],
            s["judge"]["correct"],
        ),
        reverse=True,
    )
    rows = []
    for rank, s in enumerate(ordered):
        tiebreaks = []
        for other in ordered:
            if other is s:
                continue
            if other["solved_rate"] != s["solved_rate"]:
                continue
            if other["solved_n"] != s["solved_n"]:
                # Same RATE off different sample sizes (1/2 vs 2/4). Ordered by the larger
                # solved count -- still oracle (a), still annotated: an unannotated tie-break
                # is exactly the kind of quiet decision this card exists to prevent.
                tiebreaks.append("tiebreak: larger solved count (still oracle (a))")
                continue
            if other["judge"]["correct"] != s["judge"]["correct"]:
                tiebreaks.append("tiebreak: judge (subjective)")
            else:
                tiebreaks.append("tiebreak: candidate id (deterministic, not a signal)")
        rows.append({
            "rank": rank,
            "candidate": s["candidate"],
            "solved_n": s["solved_n"],
            "objective_n": s["objective_n"],
            "solved_rate": s["solved_rate"],
            "judge_correct_n": s["judge"]["correct"],
            "tiebreaks": sorted(set(tiebreaks)),
        })
    return rows


def _tier_map(order):
    """THE RULE, step (ii): capability order -> `strong` / `mid` / `weak` (+ notes).

    More candidates than slots: every candidate past the last slot is listed as a NEAREST
    NEIGHBOUR of the slot it ranks next to -- listed, never silently dropped and never
    promoted into a slot it did not rank into. Fewer candidates than slots: the unfilled slots
    stay EMPTY with a note. A tier map is not invented for a slot nothing was measured for.
    """
    slots = {slot: None for slot in TIER_SLOTS}
    neighbours = {slot: [] for slot in TIER_SLOTS}
    notes = []
    for row in order:
        rank = row["rank"]
        if rank < len(TIER_SLOTS):
            slots[TIER_SLOTS[rank]] = row["candidate"]
        else:
            nearest = TIER_SLOTS[min(rank, len(TIER_SLOTS) - 1)]
            neighbours[nearest].append(row["candidate"])
    unfilled = [slot for slot in TIER_SLOTS if slots[slot] is None]
    if unfilled:
        notes.append(
            f"unfilled slot(s): {', '.join(unfilled)} — only {len(order)} candidate(s) were "
            f"measured in this run, so those slots stay EMPTY rather than being filled by a "
            f"model nothing ranked into"
        )
    extras = sum(len(v) for v in neighbours.values())
    if extras:
        notes.append(
            f"{len(order)} candidates for {len(TIER_SLOTS)} slots — the {extras} candidate(s) "
            f"ranking past the last slot are listed as its nearest neighbours, not promoted "
            f"into it"
        )
    return {
        "slots": slots,
        "nearest_neighbors": neighbours,
        "role_gloss": TIER_ROLE_GLOSS,
        "notes": notes,
    }


def _daily_driver(summaries, rows_by_candidate, profiles, profiles_missing):
    """THE RULE, step (iii): cheapest among the capability-equivalent, with its numbers.

    Capability-equivalence is oracle (a) ONLY, scoped to the quick-task profiles
    (`DAILY_DRIVER_PROFILES`): a candidate is eligible when its solved-count there is within
    `DAILY_DRIVER_SLACK` task(s) of the best. Among the eligible, the pick is the lowest
    `(median usd, median wall_seconds)` LEXICOGRAPHIC -- dollars first, latency only as the
    tie-break -- so a clearly-worse-capability candidate can never be bought by being cheap.
    Every number that decided it is returned for printing beside the pick.
    """
    notes = []
    scoped = {}
    for s in summaries:
        cand = s["candidate"]
        cells = rows_by_candidate.get(cand, [])
        if profiles_missing:
            in_scope = cells
        else:
            in_scope = [r for r in cells if profiles.get(r["task_id"]) in DAILY_DRIVER_PROFILES]
        scoped[cand] = {
            "candidate": cand,
            "quick_solved_n": sum(1 for r in in_scope if r["tests"]["solved"]),
            "quick_objective_n": sum(1 for r in in_scope if r["tests"]["available"]),
            "usd_median": s["cost"]["usd_median"],
            "usd_basis": s["cost"]["basis"],
            "wall_seconds_median": s["latency"]["wall_seconds_median"],
        }
    if profiles_missing:
        notes.append(NO_PROFILE_DATA_NOTE)
    else:
        unprofiled = sorted({
            r["task_id"] for cells in rows_by_candidate.values() for r in cells
            if r["task_id"] not in profiles
        })
        if unprofiled:
            notes.append(
                f"task(s) with no recorded size profile were excluded from the quick-task "
                f"scope rather than assumed small: {', '.join(unprofiled)}"
            )

    best = max((v["quick_solved_n"] for v in scoped.values()), default=0)
    for v in scoped.values():
        v["eligible"] = (v["quick_solved_n"] >= best - DAILY_DRIVER_SLACK)
        v["priced"] = v["usd_median"] is not None
    if best == 0:
        notes.append(
            "no candidate solved a single quick task objectively — the ordering below is a "
            "COST ordering among candidates with no demonstrated capability, and is not a "
            "capability finding"
        )

    eligible = [v for v in scoped.values() if v["eligible"] and v["priced"]]
    unpriced = sorted(v["candidate"] for v in scoped.values() if v["eligible"] and not v["priced"])
    if unpriced:
        notes.append(
            f"eligible but unpriced (no dispatched cell to take a median from): "
            f"{', '.join(unpriced)} — excluded from the cost comparison rather than ranked at "
            f"$0.00"
        )
    pick = None
    if eligible:
        pick = min(
            eligible,
            key=lambda v: (
                v["usd_median"],
                v["wall_seconds_median"] if v["wall_seconds_median"] is not None else float("inf"),
                v["candidate"],
            ),
        )["candidate"]
    else:
        notes.append("no eligible, priced candidate — no daily-driver pick is made")

    return {
        "pick": pick,
        "best_quick_solved_n": best,
        "slack_tasks": DAILY_DRIVER_SLACK,
        "profiles": list(DAILY_DRIVER_PROFILES),
        "profiles_available": not profiles_missing,
        "rows": [scoped[s["candidate"]] for s in summaries],
        "notes": notes,
    }


def _published_leg(candidates, benchmarks_path):
    """PLAN D10's PUBLISHED leg -> (per-candidate entries, notes, source metadata).

    `bench_routing.load_benchmarks` reads the file and `bench_routing.normalize_id` performs
    the join -- both REUSED, never re-implemented here (D10/R4). A model with several
    published rows (one per reasoning effort) is represented by its highest index, with the
    effort named, because that is the row a reader would compare against. An absent model is
    `no published entry`; an unreadable benchmarks file makes EVERY candidate absent, with a
    note -- never a fabricated index.
    """
    br = _br()
    entries = {c: {"status": NO_PUBLISHED_ENTRY, "index": None, "effort": None} for c in candidates}
    notes = []
    try:
        data = br.load_benchmarks(str(benchmarks_path))
    except (OSError, ValueError, TypeError) as e:
        notes.append(
            f"published leg unavailable: {benchmarks_path} could not be read ({e}) — every "
            f"candidate reads `{NO_PUBLISHED_ENTRY}`"
        )
        return entries, notes, {}
    best = {}
    for entry in (data.get("entries") or []):
        index = entry.get("intelligence_index")
        if index is None:
            continue
        key = br.normalize_id(entry.get("model"))
        if key not in best or index > best[key].get("intelligence_index", index - 1):
            best[key] = entry
    for candidate in candidates:
        entry = best.get(br.normalize_id(candidate))
        if entry is not None:
            entries[candidate] = {
                "status": "published",
                "index": entry.get("intelligence_index"),
                "effort": entry.get("effort"),
            }
    source = {
        "index_name": data.get("index_name"),
        "index_version": data.get("index_version"),
        "cached_date": data.get("cached_date"),
        "path": str(benchmarks_path),
    }
    return entries, notes, source


def _observed_leg(candidates, pricing, kits_dir):
    """PLAN D10's OBSERVED leg -> (per-candidate stats, notes).

    `routing_scorecard.scan_kits` + `routing_scorecard.history_tier_stats` do the parsing and
    the per-tier attribution; this function only sums their output and joins a candidate to
    its tier through `bench_routing.claude_tier_for_model`. No ledger line is parsed here.
    The leg exists ONLY when a kits dir was supplied and exists -- otherwise every candidate
    honestly reads `no ledger evidence`, which is not the same claim as a 0% rate.
    """
    stats = {c: {"status": NO_LEDGER_EVIDENCE, "tier": None, "first_try": None,
                 "with_outcome": None, "rate": None} for c in candidates}
    notes = []
    if kits_dir is None:
        return stats, notes
    kits_path = Path(kits_dir)
    if not kits_path.is_dir():
        notes.append(
            f"observed leg: no kit ledger at {kits_path} — every candidate reads "
            f"`{NO_LEDGER_EVIDENCE}` (this repo's ledger is not evidence about the TARGET)"
        )
        return stats, notes

    rs = _rs()
    br = _br()
    try:
        records, scan_notes = rs.scan_kits(kits_path)
    except (OSError, ValueError) as e:
        notes.append(f"observed leg: kit scan failed ({e}) — every candidate reads "
                     f"`{NO_LEDGER_EVIDENCE}`")
        return stats, notes
    notes.extend(scan_notes)

    agg = {}
    for record in records:
        applied = [e for e in record.get("events") or [] if e.get("mode") == "applied"]
        tier_stats, tier_notes = rs.history_tier_stats(
            record.get("tasks") or [], record.get("outcomes") or {}, applied
        )
        notes.extend(f"{record.get('kit')}: {n}" for n in tier_notes)
        for tier, s in tier_stats.items():
            bucket = agg.setdefault(tier, {"first_try": 0, "with_outcome": 0})
            bucket["first_try"] += s["first_try"]
            bucket["with_outcome"] += s["with_outcome"]

    for candidate in candidates:
        tier = br.claude_tier_for_model(candidate, pricing)
        bucket = agg.get(tier)
        if tier is None or bucket is None or not bucket["with_outcome"]:
            stats[candidate]["tier"] = tier
            continue
        rate = bucket["first_try"] / bucket["with_outcome"]
        entry = {
            "status": "observed",
            "tier": tier,
            "first_try": bucket["first_try"],
            "with_outcome": bucket["with_outcome"],
            "rate": rate,
        }
        if bucket["with_outcome"] < rs.LIVE_MIN_SAMPLE:
            entry["status"] = "observed (insufficient sample)"
            notes.append(
                f"observed leg: tier {tier} has {bucket['with_outcome']} completed task(s) in "
                f"the ledger, below routing_scorecard.LIVE_MIN_SAMPLE "
                f"({rs.LIVE_MIN_SAMPLE}) — the rate is shown with its sample, not as a finding"
            )
        stats[candidate] = entry
    return stats, notes


def _disagreements(order, published):
    """PLAN D10: where the published index INVERTS this run's measured capability order.

    Fires only on a pair where BOTH legs have a reading and BOTH have an opinion -- a
    published index cannot disagree with a measurement that does not exist, and neither leg
    is ever adjusted toward the other. The note names both directions and lets all three legs
    stand.
    """
    notes = []
    measured = [row for row in order if row["solved_rate"] is not None]
    for i, better in enumerate(measured):
        for worse in measured[i + 1:]:
            if better["solved_rate"] == worse["solved_rate"]:
                continue
            hi = published.get(better["candidate"], {}).get("index")
            lo = published.get(worse["candidate"], {}).get("index")
            if hi is None or lo is None or lo <= hi:
                continue
            notes.append(
                f"{DISAGREEMENT_PREFIX}: published index ranks {worse['candidate']} above "
                f"{better['candidate']}; this repo's measurement ranks {better['candidate']} "
                f"above {worse['candidate']}"
            )
    return notes


def _rule_text(goal, min_tasks, order, tier_map, daily_driver):
    """THE RULE, rendered as text so it is inspectable beside its own result (PLAN D5/T8).

    The point is not documentation -- it is that a reader can check the printed verdict
    against the printed rule without reading this file.
    """
    lines = [
        "THE RULE, as applied (there is no composite score; nothing below is weighted or "
        "blended):",
        "  (i) capability order = solved_n / objective_n, where solved_n counts ONLY cells "
        "whose tests oracle (a) PASSED and objective_n counts cells whose tests oracle was "
        "AVAILABLE. Counts print beside every rate: at these sample sizes a rate on its own "
        "is not readable.",
        "      ties are broken by the judge's `correct` count and annotated "
        "`tiebreak: judge (subjective)`; a remaining tie is broken by candidate id and "
        "annotated too. A subjective signal may ORDER a tie, never create one.",
        "      a candidate with objective_n = 0 has NO capability reading — it sorts last as "
        "an absence, never as a zero. The same rate off different sample sizes (1/2 vs 2/4) "
        "is ordered by the larger solved COUNT, annotated too.",
        f"  (floor) every candidate needs >= {min_tasks} objectively-scored tasks for a "
        f"routing-grade verdict (PLAN D7; `--min-tasks` can only RAISE this).",
    ]
    for row in order:
        rate = "n/a (no objectively-scored cell)" if row["solved_rate"] is None else (
            f"{row['solved_rate'] * 100:.0f}%"
        )
        annot = ("  [" + "; ".join(row["tiebreaks"]) + "]") if row["tiebreaks"] else ""
        lines.append(
            f"      -> #{row['rank'] + 1} {row['candidate']}: solved {row['solved_n']}/"
            f"{row['objective_n']} = {rate}; judge correct = {row['judge_correct_n']}{annot}"
        )

    if tier_map is not None:
        lines.append(
            f"  (ii) tier map = capability order -> {' / '.join(TIER_SLOTS)}, role gloss "
            f"{TIER_ROLE_GLOSS}."
        )
        for slot in TIER_SLOTS:
            holder = tier_map["slots"][slot] or "(empty)"
            near = tier_map["nearest_neighbors"][slot]
            near_txt = f"  nearest neighbours: {', '.join(near)}" if near else ""
            lines.append(f"      -> {slot}: {holder}{near_txt}")
        for note in tier_map["notes"]:
            lines.append(f"      note: {note}")

    if daily_driver is not None:
        scope = (
            "/".join(daily_driver["profiles"]) if daily_driver["profiles_available"]
            else "ALL tasks (size profiles unavailable — see the note)"
        )
        lines.append(
            f"  (iii) daily driver = among candidates whose solved-count on {scope} tasks is "
            f"within {daily_driver['slack_tasks']} task of the best "
            f"({daily_driver['best_quick_solved_n']}), the lowest (median usd, median "
            f"wall_seconds) lexicographic."
        )
        for row in daily_driver["rows"]:
            lines.append(
                f"      -> {row['candidate']}: quick solved {row['quick_solved_n']}/"
                f"{row['quick_objective_n']}, "
                f"eligible={row['eligible']}, median usd="
                f"{_fmt_num(row['usd_median'], '.4f')} ({row['usd_basis']}), median wall="
                f"{_fmt_num(row['wall_seconds_median'], '.2f')}s"
            )
        for note in daily_driver["notes"]:
            lines.append(f"      note: {note}")
        lines.append(f"      => pick: {daily_driver['pick'] or '(none)'}")
    return lines


def build_verdict(run_dir, goal, pricing, benchmarks_path=None, kits_dir=None, min_tasks=None):
    """PLAN D5/D7/D10's verdict card for one completed run -> a JSON-serializable dict.

    Reads `results.json` (the run's ONE envelope) and nothing else that could be a source of
    correctness: `solved` comes from oracle (a) and from nowhere else. The card carries the
    per-cell measurement rows with explicit `n/a` cells, the per-candidate summaries with
    every oracle in its own labelled class, THE RULE as text beside its own result, the
    verdict(s) the goal asked for, the three legs side by side with disagreements named, the
    envelope's own honesty labels carried forward, and the run's spend with its basis.

    `benchmarks_path` and `kits_dir` are injectable seams (tests point them at fixtures);
    `min_tasks` can only RAISE the D7 floor (`resolve_min_tasks`).
    """
    run_dir = Path(run_dir)
    if goal not in VERDICT_GOALS:
        raise ValueError(f"unknown verdict goal {goal!r}; valid: {', '.join(VERDICT_GOALS)}")
    results_path = run_dir / "results.json"
    if not results_path.exists():
        raise FileNotFoundError(
            f"no results.json in {run_dir} — a verdict is rendered from a run's envelope, "
            f"never reconstructed"
        )
    results = json.loads(results_path.read_text())
    if pricing is None:
        pricing = _cr().load_pricing()
    min_tasks = resolve_min_tasks(min_tasks)

    cells = results.get("cells") or []
    grades = _grades_index(results)
    candidates = list(results.get("candidates") or [])
    for cell in cells:
        if cell.get("model") and cell["model"] not in candidates:
            candidates.append(cell["model"])

    measurements = [
        _expand_oracles(cell, grades.get((cell.get("task_id"), cell.get("model"))))
        for cell in cells
    ]
    rows_by_candidate = {c: [] for c in candidates}
    for row in measurements:
        rows_by_candidate.setdefault(row["candidate"], []).append(row)

    summaries = [_candidate_summary(c, rows_by_candidate.get(c, [])) for c in candidates]
    order = _capability_order(summaries)

    below_floor = (not summaries) or any(s["objective_n"] < min_tasks for s in summaries)

    tier_map = _tier_map(order) if goal in ("tiers", "both") else None
    daily_driver = None
    if goal in ("daily-driver", "both"):
        profiles, profile_notes = _task_size_profiles(run_dir)
        daily_driver = _daily_driver(
            summaries, rows_by_candidate, profiles, profiles_missing=not profiles
        )
        daily_driver["notes"] = list(profile_notes) + daily_driver["notes"]

    published, published_notes, published_source = _published_leg(
        candidates, benchmarks_path or default_benchmarks_path()
    )
    observed, observed_notes = _observed_leg(candidates, pricing, kits_dir)
    disagreements = _disagreements(order, published)

    three_legs = []
    by_candidate = {s["candidate"]: s for s in summaries}
    for candidate in candidates:
        s = by_candidate[candidate]
        three_legs.append({
            "candidate": candidate,
            "published": published[candidate],
            "observed": observed[candidate],
            "measured": {
                "solved_n": s["solved_n"],
                "objective_n": s["objective_n"],
                "solved_rate": s["solved_rate"],
            },
        })

    # Labels: the envelope's own first (GRADING_FAILED / STORE_WRITE_FAILED / cost-ceiling /
    # overspend / aborted / spend basis all survive into the verdict -- a verdict rendered off
    # a partial run must carry that run's partiality), then this card's own.
    labels = list(results.get("labels") or [])
    labels.append(SOLVED_SOURCE_LABEL)
    labels.append(STRUCTURAL_LABEL)
    labels.append(JUDGE_LABEL)
    labels.append(THREE_LEGS_LABEL)
    if below_floor:
        labels.insert(0, _below_floor_label(min_tasks))
    if any(s["solved_with_test_edits"] for s in summaries):
        labels.append(SOLVED_WITH_TEST_EDITS_LABEL)
    graded = sum(1 for g in (results.get("grades") or []) if not g.get("skipped"))
    ceiling_skipped = sum(
        1 for g in (results.get("grades") or []) if g.get("skipped") == SKIPPED_COST_CEILING
    )
    if ceiling_skipped and not graded:
        labels.append(JUDGE_BUDGET_STARVED_LABEL)

    notes = list(published_notes) + list(observed_notes) + list(disagreements)

    return {
        "verdict_schema_version": VERDICT_SCHEMA_VERSION,
        "run_id": results.get("run_id"),
        "repo": results.get("repo"),
        "mode": results.get("mode"),
        "harness": results.get("harness"),
        "judge": results.get("judge"),
        "candidates": candidates,
        "goal": goal,
        "min_tasks": min_tasks,
        "below_floor": below_floor,
        "below_floor_label": _below_floor_label(min_tasks) if below_floor else None,
        "rule": _rule_text(goal, min_tasks, order, tier_map, daily_driver),
        "measurements": measurements,
        "summaries": summaries,
        "capability_order": order,
        "tier_map": tier_map,
        "daily_driver": daily_driver,
        "three_legs": three_legs,
        "published_source": published_source,
        "disagreements": disagreements,
        "spend": results.get("spend") or {},
        "labels": labels,
        "notes": notes,
    }


def _tests_cell_text(row):
    """Oracle (a) as one table cell. `n/a` when the oracle was unavailable -- the ONLY three
    strings this column may ever hold are `solved`, `not solved` and `n/a`."""
    if not row["tests"]["available"]:
        return NA
    return "solved" if row["tests"]["solved"] else "not solved"


def _judge_cell_text(row):
    """Oracle (c) as one table cell: the grade word, or `n/a` WITH the reason it is absent.

    The reason matters and the `n/a` is not negotiable: a missing grade because the budget ran
    out, a grade the parser refused to guess at, a grade deliberately not bought because the
    reference was empty, and a cell that has no grade record at all are four different facts,
    and none of them is a score.
    """
    if row["judge"]["grade"]:
        return row["judge"]["grade"]
    return f"{NA} ({row['judge']['status']})"


def _similarity_cell_text(row):
    """Oracle (b) as one table cell: `files/hunks/loc` similarity, or `n/a`. Never a zero
    standing in for an unavailable comparison."""
    s = row["structural"]
    if not s["available"]:
        return NA
    return (
        f"{_fmt_num(s['files_jaccard'])}/{_fmt_num(s['hunk_overlap'])}/"
        f"{_fmt_num(s['loc_delta_ratio'])}"
    )


def render_verdict_markdown(card):
    """The verdict card as markdown -- the human-readable half of PLAN D8's run dir.

    Section order is fixed: the below-floor stamp (when it applies) comes FIRST, before any
    number a reader could quote, and again in the labels. The measurement table prints one
    column per oracle with explicit `n/a` cells; the rule prints beside its own result; the
    three legs print side by side.
    """
    lines = [f"# repo-bench verdict — run {card['run_id']}", ""]
    if card["below_floor"]:
        lines.append(f"## {card['below_floor_label']}")
        lines.append("")
        lines.append(
            "The measurement table below still renders in full — refusing a routing-grade "
            "CLAIM is not the same as hiding the data. `apply` refuses this verdict."
        )
        lines.append("")
    lines.append(f"repo: {card['repo']}")
    lines.append(f"mode: {card['mode']}   harness: {card['harness']}   judge: {card['judge']}")
    lines.append(f"candidates: {', '.join(card['candidates']) or '(none)'}")
    lines.append(f"goal: {card['goal']}   evidence floor: {card['min_tasks']} task(s)")
    lines.append("")

    lines.append("## measurement (one column per oracle; `n/a` = that oracle was unavailable)")
    lines.append(
        "| task | candidate | (a) tests | (b) similarity files/hunks/loc | (c) judge | "
        "(d) usd | (d) wall s | touched tests | out-of-scope (excluded) | skipped |"
    )
    lines.append("|" + "---|" * 10)
    for row in card["measurements"]:
        touched = row["candidate_touched_tests"]
        touched_txt = NA if touched is None else (", ".join(touched) if touched else "-")
        # F1: the column that keeps a false negative from reading as a capability failure.
        out_of_scope = row["candidate_modified_out_of_scope"]
        oos_txt = NA if out_of_scope is None else (", ".join(out_of_scope) if out_of_scope else "-")
        usd = row["cost"]["usd"]
        usd_txt = NA if usd is None else f"{usd:.4f} ({row['cost']['usd_basis'] or NA})"
        lines.append(
            f"| {row['task_id']} | {row['candidate']} | {_tests_cell_text(row)} | "
            f"{_similarity_cell_text(row)} | {_judge_cell_text(row)} | {usd_txt} | "
            f"{_fmt_num(row['latency']['wall_seconds'])} | {touched_txt} | {oos_txt} | "
            f"{row['skipped'] or '-'} |"
        )
    lines.append("")

    lines.append("## per candidate")
    for s in card["summaries"]:
        rate = NA if s["solved_rate"] is None else f"{s['solved_rate'] * 100:.0f}%"
        lines.append(f"### {s['candidate']}")
        lines.append(
            f"  (a) solved: {s['solved_n']}/{s['objective_n']} objectively-scored cell(s) "
            f"= {rate}   [{SOLVED_SOURCE_LABEL}]"
        )
        j = s["judge"]
        lines.append(
            f"  (c) judge: correct={j['correct']} partial={j['partial']} "
            f"incorrect={j['incorrect']} {NA}={j['na']} "
            f"(unparseable={j['unparseable']}, skipped cost-ceiling="
            f"{j['skipped_cost_ceiling']}, skipped empty-reference="
            f"{j['skipped_empty_reference']}, no grade record={j['no_grade_record']})   "
            f"[{JUDGE_LABEL}]"
        )
        m = s["structural_medians"]
        lines.append(
            f"  (b) similarity medians: files={_fmt_num(m['files_jaccard'])} "
            f"hunks={_fmt_num(m['hunk_overlap'])} loc={_fmt_num(m['loc_delta_ratio'])} "
            f"over {m['available_n']} available cell(s)   [{STRUCTURAL_LABEL}]"
        )
        lines.append(
            f"  (d) cost: total ${_fmt_num(s['cost']['usd_total'], '.4f')} "
            f"(basis: {s['cost']['basis']}), median ${_fmt_num(s['cost']['usd_median'], '.4f')}; "
            f"median wall {_fmt_num(s['latency']['wall_seconds_median'])}s"
            + (
                f"; {s['cost']['usd_unpriced_n']} dispatched cell(s) carried no priced "
                f"dollars and are excluded from the total, not counted as $0"
                if s["cost"]["usd_unpriced_n"] else ""
            )
        )
        lines.append(
            f"  cells: {s['dispatched_n']} dispatched, {s['skipped_n']} skipped"
            + (f" ({', '.join(s['skipped_reasons'])})" if s["skipped_reasons"] else "")
        )
        if s["solved_with_test_edits"]:
            lines.append(
                f"  NOTE — solved WITH test-file edits on: "
                f"{', '.join(s['solved_with_test_edits'])} (the grade substrate is constructed "
                f"from the base state, so those edits were never applied and did not earn "
                f"the pass)"
            )
        if s["not_solved_with_out_of_scope"]:
            lines.append(
                f"  NOTE — `not solved` WITH work reverted from outside the reference patch's "
                f"scope on: {', '.join(s['not_solved_with_out_of_scope'])}. "
                f"{CANDIDATE_OUT_OF_SCOPE_NOTE} Read those cell(s) as possible FALSE "
                f"NEGATIVES: the reverted paths are in the measurement table, and a fix that "
                f"lived only there was undone before the test command ran."
            )
        lines.append("")

    lines.append("## the rule, as applied")
    lines.extend(f"  {line}" if line.startswith("  ") else line for line in card["rule"])
    lines.append("")

    lines.append("## verdict")
    if card["below_floor"]:
        lines.append(f"  {card['below_floor_label']}")
    if card["tier_map"] is not None:
        tm = card["tier_map"]
        lines.append(f"  tier map ({tm['role_gloss']}):")
        for slot in TIER_SLOTS:
            holder = tm["slots"][slot] or "(empty)"
            near = tm["nearest_neighbors"][slot]
            lines.append(
                f"    {slot}: {holder}"
                + (f"   nearest neighbours: {', '.join(near)}" if near else "")
            )
        for note in tm["notes"]:
            lines.append(f"    note: {note}")
    if card["daily_driver"] is not None:
        dd = card["daily_driver"]
        lines.append(f"  daily driver: {dd['pick'] or '(none)'}")
        for note in dd["notes"]:
            lines.append(f"    note: {note}")
    lines.append("")

    lines.append("## three legs (PLAN D10 — never merged into one number)")
    src = card["published_source"] or {}
    if src.get("index_name"):
        lines.append(
            f"published prior: {src['index_name']} {src.get('index_version') or ''} "
            f"(cached {src.get('cached_date') or 'unknown'}) — a published index, not this "
            f"repo's measurement"
        )
    lines.append("| candidate | published index | observed first-try (ledger) | measured (this run) |")
    lines.append("|" + "---|" * 4)
    for leg in card["three_legs"]:
        pub = leg["published"]
        pub_txt = (
            NO_PUBLISHED_ENTRY if pub["index"] is None
            else f"{pub['index']} ({pub.get('effort') or 'n/a effort'})"
        )
        obs = leg["observed"]
        obs_txt = (
            NO_LEDGER_EVIDENCE if obs["rate"] is None
            else f"{obs['first_try']}/{obs['with_outcome']} = {obs['rate'] * 100:.0f}% "
                 f"(tier {obs['tier']}; {obs['status']})"
        )
        meas = leg["measured"]
        meas_txt = (
            NA if meas["solved_rate"] is None
            else f"solved {meas['solved_n']}/{meas['objective_n']} = "
                 f"{meas['solved_rate'] * 100:.0f}%"
        )
        lines.append(f"| {leg['candidate']} | {pub_txt} | {obs_txt} | {meas_txt} |")
    lines.append("")
    for note in card["disagreements"]:
        lines.append(note)
    if card["disagreements"]:
        lines.append("")

    lines.append("## labels")
    for label in card["labels"]:
        lines.append(f"label: {label}")
    lines.append("")
    if card["notes"]:
        lines.append("## notes")
        for note in card["notes"]:
            lines.append(f"note: {note}")
        lines.append("")

    spend = card["spend"] or {}
    lines.append("## spend")
    lines.append(
        f"  recorded ${_fmt_num(spend.get('spent_usd'), '.4f')} against a "
        f"${_fmt_num(spend.get('ceiling_usd'), '.4f')} ceiling "
        f"(basis: {spend.get('basis') or NA})"
    )
    basis = spend.get("basis")
    if basis in SPEND_BASIS_LABELS:
        lines.append(f"  {SPEND_BASIS_LABELS[basis]}")
    return "\n".join(lines)


def cmd_verdict(args):
    """Render a run's verdict to `verdict.md` (and stdout), and fold it into results.json.

    `bin/repo_bench.py` stays the store's ONE writer (PLAN D8): the envelope is re-read,
    the `"verdict"` key is set, and the whole thing is written back through `json` -- never
    patched textually, never hand-authored, never backdated.
    """
    store_dir = Path(args.store_dir) if args.store_dir else DEFAULT_STORE_DIR
    run_dir = store_dir / args.run
    if not run_dir.is_dir():
        raise FileNotFoundError(
            f"no run {args.run!r} in the benchruns store at {store_dir} — `list` shows what "
            f"is there"
        )

    kits_dir = args.kits_dir
    if kits_dir is None:
        # PLAN D10: the observed leg is the TARGET's own ledger, when it has one.
        try:
            repo = json.loads((run_dir / "results.json").read_text()).get("repo")
        except (json.JSONDecodeError, UnicodeDecodeError, OSError, AttributeError):
            repo = None
        if repo:
            candidate_kits = Path(repo) / ".claude" / "kits"
            kits_dir = str(candidate_kits) if candidate_kits.is_dir() else None

    card = build_verdict(
        run_dir, args.goal, None,
        benchmarks_path=args.benchmarks, kits_dir=kits_dir, min_tasks=args.min_tasks,
    )
    markdown = render_verdict_markdown(card)
    (run_dir / "verdict.md").write_text(markdown + "\n")

    results_path = run_dir / "results.json"
    results = json.loads(results_path.read_text())
    results["verdict"] = {
        "verdict_schema_version": card["verdict_schema_version"],
        "goal": card["goal"],
        "min_tasks": card["min_tasks"],
        "below_floor": card["below_floor"],
        "below_floor_label": card["below_floor_label"],
        "rule": card["rule"],
        "capability_order": card["capability_order"],
        "tier_map": card["tier_map"],
        "daily_driver": card["daily_driver"],
        "three_legs": card["three_legs"],
        "disagreements": card["disagreements"],
        "labels": card["labels"],
        "notes": card["notes"],
    }
    results_path.write_text(json.dumps(results, indent=2) + "\n")

    # F4 (Phase 4 review): `--json` means MACHINE-READABLE, and stdout used to carry the JSON
    # body followed by a blank line and `verdict.md: <path>` -- so `json.loads` died with
    # `Extra data` while `plan --json` and `list --json` both parsed. The receipt is still
    # printed (it is useful, and a human running with `--json` still wants it) but on stderr,
    # where it cannot corrupt the document stdout is now promising to be.
    if args.json:
        print(json.dumps(card, indent=2))
        print(f"verdict.md: {run_dir / 'verdict.md'}", file=sys.stderr)
    else:
        print(markdown)
        print("")
        print(f"verdict.md: {run_dir / 'verdict.md'}")
    return 0


# ---------------------------------------------------------------------------------------------
# demo: fully synthetic sandbox + capture smoke. No model, no network, no money, and nothing
# written outside its own temp dir.


def _fixture_git(root, *args, git_runner=None):
    """Git against a fixture repo THIS MODULE builds from nothing, in its own temp dir.

    Deliberately NOT `git_sandbox`: the demo hands its fixture to `make_sandbox` one line
    later and calls it a "target", and `git_sandbox` naming a target -- even a synthetic,
    seconds-old, temp-dir one -- would blur the module-wide reading that `git_sandbox` only
    ever touches sandboxes WE built for a candidate. Same identity pinning, same freedom
    from any allowlist (we are creating this repo, not reading someone's).
    """
    runner = git_runner or default_git_runner
    return runner(["git", "-C", str(root), *SANDBOX_GIT_CONFIG, *args])


#: The demo fixture's bug and its fix. The stub test runner below grades on the presence of
#: `DEMO_FIXED_LINE` in `calc.py`, so one demo candidate can genuinely read GREEN through the
#: real oracle-(a) path and the other genuinely RED -- neither is asserted, both are measured.
DEMO_BUGGY_LINE = "    return a - b\n"
DEMO_FIXED_LINE = "    return a + b\n"


def _build_demo_repo(root, git_runner=None):
    """A throwaway two-commit fixture repo, built with `_fixture_git` (see above).

    Shaped for issue-replay, with BOTH shapes a verdict has to render honestly:
      * commit 2 (`(#7)`) fixes the bug in `calc.py` AND touches a test file, so its mined
        task carries real test blobs and oracle (a) is genuinely AVAILABLE;
      * commit 3 (`(#9)`) touches no test at all, so its task's tests oracle is genuinely
        UNAVAILABLE and every cell of it must render `n/a` -- never a dropped row, never a
        zero. A demo that only ever showed the happy oracle would be advertising, not a smoke.
    `SECRET_FIX.md` rides on the fix commit as the leak canary part 1 checks for.

    Returns `(head, base_of_fix)` -- the SECOND value is the pre-fix commit, named rather than
    derived as `HEAD~1`, because commits added after it must not silently move it.
    """
    root.mkdir(parents=True, exist_ok=True)
    _require_ok(*_fixture_git(root, "init", "-q", git_runner=git_runner), "demo git init")
    (root / "calc.py").write_text(f"def add(a, b):\n{DEMO_BUGGY_LINE}")
    (root / "README.md").write_text("# demo fixture\n")
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests" / "test_calc.py").write_text("# the base test surface\n")
    _require_ok(*_fixture_git(root, "add", "-A", git_runner=git_runner), "demo git add")
    _require_ok(
        *_fixture_git(root, "commit", "-q", "-m", "first", git_runner=git_runner), "demo commit"
    )
    rc, out = _fixture_git(root, "rev-parse", "HEAD", git_runner=git_runner)
    _require_ok(rc, out, "demo rev-parse base")
    base_of_fix = out.strip()

    (root / "calc.py").write_text(f"def add(a, b):\n{DEMO_FIXED_LINE}")
    (root / "tests" / "test_calc.py").write_text(
        "# the fix commit's test blob — withheld from every candidate sandbox\n"
        "assert __import__('calc').add(1, 1) == 2\n"
    )
    (root / "SECRET_FIX.md").write_text("the reference fix would live in history\n")
    _require_ok(*_fixture_git(root, "add", "-A", git_runner=git_runner), "demo git add 2")
    _require_ok(
        *_fixture_git(root, "commit", "-q", "-m", "second: fix add (#7)", git_runner=git_runner),
        "demo commit 2",
    )

    (root / "README.md").write_text("# demo fixture\n\nnow with a usage section\n")
    _require_ok(*_fixture_git(root, "add", "-A", git_runner=git_runner), "demo git add 3")
    _require_ok(
        *_fixture_git(root, "commit", "-q", "-m", "third: document usage (#9)",
                      git_runner=git_runner),
        "demo commit 3",
    )
    rc, out = _fixture_git(root, "rev-parse", "HEAD", git_runner=git_runner)
    _require_ok(rc, out, "demo rev-parse")
    return out.strip(), base_of_fix


#: Part 4's fixture (F2, Phase 4 review). `calc.py` carries a live `>=` mutation site;
#: `run_tests.py` is the HARNESS -- and `_matches_test_pattern("run_tests.py", ...)` is False,
#: which is exactly the F1 surface: a file the test command depends on that no test-pattern
#: list names. The demo forges through it on purpose and shows the sweep catching it.
DEMO_GENERAL_FIXED = "x >= 10"
DEMO_GENERAL_MUTATED = "x > 10"
DEMO_FORGED_HARNESS = "# FORGED: the harness was rewritten instead of the bug\n"

#: Part 5's `--setup-cmd` fixture (F9, T17R). Deliberately not a real command name, and the
#: "install" is one file written by a stub runner -- `npm`, `pip` and the network are never
#: invoked by this demo, exactly as no real test suite is.
DEMO_SETUP_CMD = "demo-setup"
DEMO_SETUP_ARTIFACT = "vendor/installed.txt"
DEMO_SETUP_ARTIFACT_BODY = "demo dependencies installed\n"


def _build_demo_general_repo(root, git_runner=None):
    """A one-commit fixture the GENERAL (mutation-repair) miner can actually work on.

    Deliberately separate from `_build_demo_repo`: that one is shaped for issue-replay (two
    fix commits, withheld test blobs, a leak canary) and general mode needs something else
    entirely -- a mutatable source line at HEAD plus a harness file whose name matches no test
    pattern. Returns HEAD.
    """
    root.mkdir(parents=True, exist_ok=True)
    _require_ok(*_fixture_git(root, "init", "-q", git_runner=git_runner), "demo-general init")
    (root / "calc.py").write_text(
        "def classify(x):\n"
        f"    if {DEMO_GENERAL_FIXED}:\n"
        '        return "big"\n'
        '    return "small"\n'
    )
    (root / "run_tests.py").write_text("# the harness the repo's --test-cmd invokes\n")
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests" / "test_classify.py").write_text("# the repo's own visible test\n")
    _require_ok(*_fixture_git(root, "add", "-A", git_runner=git_runner), "demo-general add")
    _require_ok(
        *_fixture_git(root, "commit", "-q", "-m", "classify", git_runner=git_runner),
        "demo-general commit",
    )
    rc, out = _fixture_git(root, "rev-parse", "HEAD", git_runner=git_runner)
    _require_ok(rc, out, "demo-general rev-parse")
    return out.strip()


def cmd_demo(args):
    lines = []
    with tempfile.TemporaryDirectory(prefix="repo-bench-demo-") as tmp:
        tmp = Path(tmp)
        target = tmp / "target-repo"
        head, base_of_fix = _build_demo_repo(target)

        # target state BEFORE we touch it
        before_head = _require_ok(*git_target(target, "rev-parse", "HEAD"), "rev-parse").strip()
        before_log = _require_ok(*git_target(target, "log", "--oneline"), "log")
        before_status = _require_ok(*git_target(target, "status", "--porcelain"), "status")

        sandbox = make_sandbox(target, base_of_fix, tmp / "work" / "cell-1")

        rc, out = git_sandbox(sandbox["path"], "rev-list", "--count", "HEAD")
        _require_ok(rc, out, "sandbox rev-list")
        commit_count = out.strip()
        leaked = (Path(sandbox["path"]) / "SECRET_FIX.md").exists()

        after_head = _require_ok(*git_target(target, "rev-parse", "HEAD"), "rev-parse").strip()
        after_status = _require_ok(*git_target(target, "status", "--porcelain"), "status")

        # case 1: the candidate leaves work uncommitted
        (Path(sandbox["path"]) / "new_uncommitted.py").write_text("x = 1\n")
        patch_uncommitted = capture_patch(sandbox["path"])

        # case 2: the candidate commits its work
        (Path(sandbox["path"]) / "new_committed.py").write_text("y = 2\n")
        _require_ok(*git_sandbox(sandbox["path"], "add", "-A"), "sandbox add")
        _require_ok(
            *git_sandbox(sandbox["path"], "commit", "-q", "-m", "candidate work"),
            "sandbox commit",
        )
        patch_committed = capture_patch(sandbox["path"])

        lines.append("repo_bench demo — synthetic sandbox + patch-capture smoke")
        lines.append(f"  fixture target repo: {target} (3 commits, throwaway, temp dir only)")
        lines.append(
            f"  base commit benchmarked: {base_of_fix[:8]} (the pre-fix commit); "
            f"HEAD is {head[:8]}"
        )
        lines.append("")
        lines.append("proved:")
        lines.append(
            f"  1. sandbox is history-free: rev-list --count HEAD = {commit_count} "
            f"(exactly one commit, init {sandbox['init_commit'][:8]})"
        )
        lines.append(
            f"  2. no solution leak: SECRET_FIX.md (added by the LATER commit) present in "
            f"sandbox = {leaked}"
        )
        lines.append(
            f"  3. target untouched: HEAD {before_head[:8]} -> {after_head[:8]}, "
            f"status --porcelain {'empty' if not after_status.strip() else 'DIRTY'} "
            f"(before: {'empty' if not before_status.strip() else 'DIRTY'}, "
            f"{len(before_log.splitlines())} commits still in its log)"
        )
        lines.append(
            f"  4. capture_patch sees UNCOMMITTED work: new_uncommitted.py in patch = "
            f"{'new_uncommitted.py' in patch_uncommitted}"
        )
        lines.append(
            f"  5. capture_patch sees COMMITTED work too: new_committed.py in patch = "
            f"{'new_committed.py' in patch_committed}"
        )
        lines.append(
            f"  6. target access allowlist enforced: {', '.join(READ_ONLY_GIT)} "
            f"(any other verb raises)"
        )
        lines.append("")
        print("\n".join(lines))

        # ---- part 2: a STUBBED end-to-end run (PLAN D1/D2) ------------------------------
        # Same loop a live run takes, with an injected runner in place of the harness: no
        # binary, no network, no money. TWO candidates, and the stub makes them genuinely
        # different: one writes the fixing change (so the tests oracle can read GREEN through
        # its real code path) and one writes an unrelated file (so it reads RED). Neither
        # outcome is asserted anywhere -- both are measured by the same oracles a live run
        # uses. The canned result envelope carries token counts, so the recorded dollars carry
        # `usd_basis: actual`, priced from data/pricing.json at run time.
        pricing = _cr().load_pricing()
        ce = _ce()
        solver_id = ce.resolve_model(pricing, "haiku")
        laggard_id = ce.resolve_model(pricing, "sonnet")
        dispatch_argvs = []
        judge_argvs = []

        def _demo_judge_output(prompt):
            """A stub judge that actually reads the two blind slots (PLAN D6).

            It grades whichever slot carries the fix -- so the demo's judge column is
            produced by the SLOT mechanism, not by a canned answer that would be right by
            luck half the time. It is still a stub: no model, no network, no money.
            """
            after_a = prompt.partition("Patch A:")[2]
            slot_a, _, slot_b = after_a.partition("Patch B:")
            fixed = DEMO_FIXED_LINE.strip()
            grade_a = "correct" if fixed in slot_a else "incorrect"
            grade_b = "correct" if fixed in slot_b else "incorrect"
            equivalent = "yes" if grade_a == grade_b else "no"
            return (
                f"GRADE A={grade_a} B={grade_b} EQUIVALENT={equivalent}\n"
                "Rationale: stub judge — graded by reading the two slots it was handed.\n"
                + json.dumps({
                    "type": "result", "subtype": "success",
                    "usage": {"input_tokens": 900, "output_tokens": 60},
                })
            )

        def demo_runner(argv, cwd):
            prompt = argv[-1]
            if "Patch A:" in prompt:            # a judge grade, not a candidate dispatch
                judge_argvs.append(argv)
                return 0, _demo_judge_output(prompt)
            dispatch_argvs.append(argv)
            model = argv[argv.index("--model") + 1] if "--model" in argv else None
            if model == solver_id:
                (Path(cwd) / "calc.py").write_text(f"def add(a, b):\n{DEMO_FIXED_LINE}")
                (Path(cwd) / "demo_candidate_fix.py").write_text("# the candidate's change\n")
            else:
                (Path(cwd) / "demo_candidate_notes.py").write_text("# looked around, gave up\n")
            return 0, json.dumps({
                "type": "result",
                "subtype": "success",
                "usage": {"input_tokens": 1200, "output_tokens": 300},
            })

        def demo_test_runner(cmd, cwd):
            """The target's `--test-cmd`, stubbed: deterministic on the CONTENT of the tree it
            is handed, so oracle (a) grades the candidate's real work without running anything
            (PLAN D11 -- the demo never executes a target repo's arbitrary test command)."""
            calc = Path(cwd) / "calc.py"
            if not calc.exists():
                return 1, "FAIL: calc.py is missing"
            return (0, "OK") if DEMO_FIXED_LINE in calc.read_text() else (1, "FAIL: add() is wrong")

        store = tmp / "store"
        run_args = build_parser().parse_args([
            "run", "--repo", str(target), "--models", "haiku,sonnet",
            "--mode", "issue-replay", "--test-cmd", "demo-tests",
            "--store-dir", str(store), "--live", "--max-usd", "1000",
        ])
        print("")
        print("repo_bench demo — stubbed end-to-end run (injected runner; nothing dispatched)")
        print("")
        cmd_run(run_args, runner=demo_runner, test_runner=demo_test_runner)

        rows, _notes = list_runs(store)
        run_id = rows[0]["run_id"]
        run_dir = Path(rows[0]["path"])
        results = json.loads((run_dir / "results.json").read_text())
        used_output_format = bool(dispatch_argvs) and all(
            argv_carries_output_format(argv) for argv in (*dispatch_argvs, *judge_argvs)
        )
        before_run_head = after_head
        final_head = _require_ok(*git_target(target, "rev-parse", "HEAD"), "rev-parse").strip()
        final_status = _require_ok(*git_target(target, "status", "--porcelain"), "status")

        print("")
        print("proved (run):")
        print(
            f"  7. every dispatch went through the INJECTED runner: "
            f"{len(dispatch_argvs)} candidate argv(s) + {len(judge_argvs)} judge argv(s) "
            f"built, 0 real binaries invoked"
        )
        print(
            f"  8. every argv carried {' '.join(OUTPUT_FORMAT_ARGS)}: {used_output_format} "
            f"(argv shape reused from claude_execute.build_dispatch, never re-derived)"
        )
        print(
            f"  9. target still untouched by the whole run: HEAD "
            f"{before_run_head[:8]} -> {final_head[:8]}, status --porcelain "
            f"{'empty' if not final_status.strip() else 'MUTATED'}"
        )
        print(
            f"  10. spend recorded with its basis: ${results['spend']['spent_usd']:.4f} "
            f"basis={results['spend']['basis']} against a "
            f"${results['spend']['ceiling_usd']:.4f} ceiling"
        )
        print(
            f"  11. patches captured: "
            f"{sum(1 for c in results['cells'] if (c.get('patch') or '').strip())}"
            f"/{len(results['cells'])} cell(s); judge grades recorded: "
            f"{len(results['grades'])}"
        )

        # ---- part 3: the verdict (PLAN D5/D7/D10) ---------------------------------------
        # The whole pipeline ends here. The demo's single task is DELIBERATELY below the
        # evidence floor: what it demonstrates is the refusal, honestly stamped, with the
        # measurement table still rendered underneath it.
        print("")
        print("repo_bench demo — verdict (below the evidence floor, and saying so)")
        print("")
        verdict_args = build_parser().parse_args([
            "verdict", "--run", run_id, "--store-dir", str(store), "--goal", "both",
        ])
        cmd_verdict(verdict_args)

        card = json.loads((run_dir / "results.json").read_text())["verdict"]
        verdict_md = (run_dir / "verdict.md").read_text()
        by_candidate = {
            row["candidate"]: row for row in card["capability_order"]
        }
        solver_row = by_candidate.get(solver_id, {})
        laggard_row = by_candidate.get(laggard_id, {})
        published_legs = sum(
            1 for leg in card["three_legs"] if leg["published"]["index"] is not None
        )
        observed_legs = sum(1 for leg in card["three_legs"] if leg["observed"]["rate"] is not None)
        # Counted out of the rendered measurement TABLE, not out of the whole document: the
        # claim is "an unavailable oracle rendered a cell that says n/a", and prose mentioning
        # `n/a` must not be able to inflate it.
        table = verdict_md.partition("## measurement")[2].partition("## per candidate")[0]
        na_cells = sum(
            1
            for line in table.splitlines() if line.startswith("| ")
            for cell in line.strip("|").split(" | ")
            if cell.strip() == NA or cell.strip().startswith(f"{NA} (")
        )

        print("")
        print("proved (verdict):")
        print(
            f"  12. below the evidence floor, stamped and not softened: "
            f"below_floor={card['below_floor']} — {card['below_floor_label']}"
        )
        print(
            f"  13. `solved` came from oracle (a) and nothing else: {solver_id} solved "
            f"{solver_row.get('solved_n')}/{solver_row.get('objective_n')} (judge correct = "
            f"{solver_row.get('judge_correct_n')}); {laggard_id} solved "
            f"{laggard_row.get('solved_n')}/{laggard_row.get('objective_n')} (judge correct = "
            f"{laggard_row.get('judge_correct_n')}) — separate columns, never summed"
        )
        print(
            f"  14. an unavailable oracle renders `{NA}`, never 0.00, and its row is never "
            f"dropped: {na_cells} `{NA}` cell(s) across "
            f"{len(card['capability_order'])} candidate(s) in verdict.md's measurement table"
        )
        print(
            f"  15. three legs stand side by side (PLAN D10): {len(card['three_legs'])} "
            f"candidate row(s) — published entries: {published_legs}, ledger evidence: "
            f"{observed_legs}, measured: {len(card['three_legs'])}; disagreements named: "
            f"{len(card['disagreements'])}"
        )
        print(
            f"  16. verdict.md written under the run dir only: "
            f"{(run_dir / 'verdict.md').exists()} ({run_dir / 'verdict.md'})"
        )

        # ---- part 4: GENERAL (mutation-repair) mode ---------------------------------------
        # F2 (Phase 4 review): PLAN's Done-means clause 1 says the demo exercises BOTH
        # acquisition modes and the skill told users the same, while `cmd_demo` hardcoded
        # `--mode issue-replay`. The capability was real and unit-tested; only its own
        # acceptance surface omitted it. Same rules as everything above: fixture repo, injected
        # runner, stub test command, temp dir only, no model, no network, no money.
        #
        # It doubles as the F1 demonstration, because general mode is where the forgery is
        # cleanest to show: one candidate repairs the injected bug, the other leaves it alone
        # and rewrites `run_tests.py` -- a file the test command depends on and NO test pattern
        # names. Neither outcome is asserted; both are measured by the real oracles.
        general_target = tmp / "general-target"
        _build_demo_general_repo(general_target)
        general_dispatch_argvs = []

        def general_runner(argv, cwd):
            prompt = argv[-1]
            cwd = Path(cwd)
            if "Patch A:" in prompt:
                after_a = prompt.partition("Patch A:")[2]
                slot_a, _, slot_b = after_a.partition("Patch B:")
                grade_a = "correct" if DEMO_GENERAL_FIXED in slot_a else "incorrect"
                grade_b = "correct" if DEMO_GENERAL_FIXED in slot_b else "incorrect"
                return 0, (
                    f"GRADE A={grade_a} B={grade_b} "
                    f"EQUIVALENT={'yes' if grade_a == grade_b else 'no'}\n"
                    "Rationale: stub judge — graded by reading the two slots it was handed.\n"
                    + json.dumps({
                        "type": "result", "subtype": "success",
                        "usage": {"input_tokens": 900, "output_tokens": 60},
                    })
                )
            general_dispatch_argvs.append(argv)
            model = argv[argv.index("--model") + 1] if "--model" in argv else None
            calc = cwd / "calc.py"
            if model == solver_id:
                calc.write_text(
                    calc.read_text().replace(DEMO_GENERAL_MUTATED, DEMO_GENERAL_FIXED)
                )
            else:
                (cwd / "run_tests.py").write_text(DEMO_FORGED_HARNESS)
            return 0, json.dumps({
                "type": "result", "subtype": "success",
                "usage": {"input_tokens": 1200, "output_tokens": 300},
            })

        def general_test_runner(cmd, cwd):
            """The target's `--test-cmd`, stubbed -- and it really does depend on the harness
            file, which is what makes the forgery above a forgery rather than a pantomime."""
            cwd = Path(cwd)
            harness = cwd / "run_tests.py"
            if harness.exists() and "FORGED" in harness.read_text():
                return 0, "OK — but only because run_tests.py was rewritten"
            calc = cwd / "calc.py"
            if not calc.exists():
                return 1, "FAIL: calc.py is missing"
            return (
                (1, "FAIL: classify(10) is no longer big")
                if DEMO_GENERAL_MUTATED in calc.read_text() else (0, "OK")
            )

        general_store = tmp / "store-general"
        general_args = build_parser().parse_args([
            "run", "--repo", str(general_target), "--models", "haiku,sonnet",
            "--mode", "general", "--test-cmd", "demo-general-tests", "--limit", "1",
            "--store-dir", str(general_store), "--live", "--max-usd", "1000",
        ])
        print("")
        print(
            "repo_bench demo — GENERAL (mutation-repair) mode, stubbed end to end "
            "(the second acquisition mode; nothing dispatched)"
        )
        print("")
        cmd_run(general_args, runner=general_runner, test_runner=general_test_runner)

        general_run_dir = Path(list_runs(general_store)[0][0]["path"])
        general_results = json.loads((general_run_dir / "results.json").read_text())
        general_tasks = [
            json.loads(p.read_text()) for p in sorted((general_run_dir / "tasks").glob("*.json"))
        ]
        general_cells = [c for c in general_results["cells"] if not c.get("skipped")]
        solver_cell = next((c for c in general_cells if c["model"] == solver_id), None)
        forger_cell = next((c for c in general_cells if c["model"] == laggard_id), None)
        general_final_status = _require_ok(
            *git_target(general_target, "status", "--porcelain"), "status"
        )

        print("")
        print("proved (general mode):")
        print(
            f"  17. the SECOND acquisition mode really ran: mode={general_results['mode']}, "
            f"{len(general_tasks)} red-validated mutation-repair task(s) generated "
            f"(the reverse-mutation diff is the reference patch; every mutation was proved "
            f"RED by the test command before the task was admitted, at zero model cost)"
        )
        print(
            f"  18. a genuine repair reads through the real oracle (a): {solver_id} "
            f"tests.passed="
            f"{solver_cell and solver_cell['oracles']['tests']['passed']} "
            f"over {len(general_cells)} dispatched cell(s)"
        )
        forged_paths = (forger_cell or {}).get("candidate_modified_out_of_scope")
        print(
            f"  19. `solved` is not forgeable through the test HARNESS (F1): {laggard_id} "
            f"rewrote run_tests.py — which matches no test pattern "
            f"(_matches_test_pattern -> "
            f"{_matches_test_pattern('run_tests.py', DEFAULT_TEST_PATTERNS)}) — and reads "
            f"tests.passed={forger_cell and forger_cell['oracles']['tests']['passed']}. The "
            f"substrate is CONSTRUCTED (base state + in-scope hunks + test blobs), so the "
            f"rewrite was never applied rather than detected; out-of-scope paths RECORDED as "
            f"evidence: {forged_paths}"
        )
        print(
            f"  20. the general-mode target is untouched too: status --porcelain "
            f"{'empty' if not general_final_status.strip() else 'MUTATED'}; "
            f"{len(general_dispatch_argvs)} candidate argv(s) through the injected runner, "
            f"0 real binaries invoked"
        )
        # ---- part 5: --setup-cmd, and the artifact store a candidate must not reach ------
        # F9 (T17R): `--setup-cmd` is a new INPUT to the grade substrate and the Done-means
        # smoke never exercised it. It is shown here with both of T17R's mechanisms visible:
        # the captured artifacts are out of a candidate's reach for the whole run, AND they are
        # content-hashed and re-verified before every overlay. Same rules as everything above:
        # fixture repo, injected runners, stub "install" (never a real npm/pip/network), temp
        # dir only, no model, no money.
        setup_target = tmp / "setup-target"
        setup_head = _build_demo_general_repo(setup_target)
        raider_found = []

        def setup_runner(cmd, cwd):
            """BOTH stubbed seams: the stub install, and the target's stub test command."""
            cwd = Path(cwd)
            if cmd == DEMO_SETUP_CMD:
                artifact = cwd / DEMO_SETUP_ARTIFACT
                artifact.parent.mkdir(parents=True, exist_ok=True)
                artifact.write_text(DEMO_SETUP_ARTIFACT_BODY)
                return 0, "stub setup installed 1 dependency"
            artifact = cwd / DEMO_SETUP_ARTIFACT
            if not artifact.exists():
                return 3, "FAIL: dependencies are not installed (run the setup command first)"
            if DEMO_FORGED_HARNESS.strip() in artifact.read_text():
                return 0, "OK — but only because the installed artifact was rewritten"
            calc = cwd / "calc.py"
            if not calc.exists():
                return 1, "FAIL: calc.py is missing"
            return (
                (1, "FAIL: classify(10) is no longer big")
                if DEMO_GENERAL_MUTATED in calc.read_text() else (0, "OK")
            )

        def setup_dispatch_runner(argv, cwd):
            """One candidate repairs the injected bug; the other tries the T17R forgery --
            reach OUT of its own sandbox for the shared setup artifacts every grade substrate
            is built from, and rewrite them. It records what it could reach."""
            cwd = Path(cwd)
            if not (cwd / "calc.py").exists():
                return 0, json.dumps({
                    "type": "result", "subtype": "success",
                    "usage": {"input_tokens": 900, "output_tokens": 60},
                })
            model = argv[argv.index("--model") + 1] if "--model" in argv else None
            if model == solver_id:
                calc = cwd / "calc.py"
                calc.write_text(
                    calc.read_text().replace(DEMO_GENERAL_MUTATED, DEMO_GENERAL_FIXED)
                )
            else:
                for depth in ("..", "../.."):
                    root = (cwd / depth).resolve()
                    for path in sorted(root.rglob("*")):
                        if not path.is_file():
                            continue
                        try:
                            text = path.read_text()
                        except (UnicodeDecodeError, OSError):
                            continue
                        if DEMO_SETUP_ARTIFACT_BODY in text:
                            raider_found.append(str(path.relative_to(root)))
                            path.write_text(DEMO_FORGED_HARNESS)
            return 0, json.dumps({
                "type": "result", "subtype": "success",
                "usage": {"input_tokens": 1200, "output_tokens": 300},
            })

        setup_store = tmp / "store-setup"
        setup_args = build_parser().parse_args([
            "run", "--repo", str(setup_target), "--models", "haiku,sonnet",
            "--mode", "general", "--test-cmd", "demo-setup-tests",
            "--setup-cmd", DEMO_SETUP_CMD, "--limit", "1",
            "--store-dir", str(setup_store), "--live", "--max-usd", "1000",
            "--keep-work",
        ])
        print("")
        print(
            "repo_bench demo — --setup-cmd: a target that must install before its tests run "
            "(stubbed install; no npm, no pip, no network)"
        )
        print("")
        cmd_run(setup_args, runner=setup_dispatch_runner, test_runner=setup_runner)

        setup_run_dir = Path(list_runs(setup_store)[0][0]["path"])
        setup_results = json.loads((setup_run_dir / "results.json").read_text())
        setup_cells = [c for c in setup_results["cells"] if not c.get("skipped")]
        setup_solver = next((c for c in setup_cells if c["model"] == solver_id), None)
        setup_raider = next((c for c in setup_cells if c["model"] == laggard_id), None)
        artifacts_under_run_dir = [
            str(p.relative_to(setup_run_dir)) for p in setup_run_dir.rglob("*")
            if p.is_file() and p.name == Path(DEMO_SETUP_ARTIFACT).name
        ]

        # The second mechanism, on its own: the store is out of a candidate's reach, so it is
        # reached HERE, from inside the tool, and the content hashes are what refuse the grade.
        tamper_task = {
            "task_id": "demo-tamper", "mode": "general", "oracle_tests_available": True,
            "test_blobs": {}, "base_commit": setup_head, "setup_patch": None,
            "reference_patch": (
                "--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n-old\n+new\n"
            ),
        }
        tamper_templates = GradeTemplates(
            setup_target, tmp / "tamper-templates", DEMO_SETUP_CMD, test_runner=setup_runner,
        )
        tamper_record = tamper_templates.prepare(tamper_task)
        (Path(tamper_record["path"]) / DEMO_SETUP_ARTIFACT).write_text(DEMO_FORGED_HARNESS)
        tamper_oracle = oracle_tests(
            tamper_task, "", "demo-setup-tests", setup_runner, tmp / "tamper-scratch",
            target_repo=setup_target, templates=tamper_templates,
        )
        tamper_templates.cleanup()

        print("")
        print("proved (--setup-cmd):")
        print(
            f"  21. a target that cannot run its tests until something is installed is "
            f"gradable: {setup_results['setup']['templates_prepared']} template(s) prepared, "
            f"reused across {setup_results['setup']['gradings_served']} grading(s); "
            f"{setup_results['setup']['setup_seconds']:.3f}s of setup time recorded separately "
            f"from every cell's wall_seconds; a genuine repair reads tests.passed="
            f"{setup_solver and setup_solver['oracles']['tests']['passed']}"
        )
        print(
            f"  22. the artifact store is out of a candidate's reach (T17R/F1): the second "
            f"candidate swept ../ and ../../ of its own sandbox for the installed artifacts and "
            f"found {len(raider_found)}; it changed nothing in its sandbox and reads "
            f"tests.passed={setup_raider and setup_raider['oracles']['tests']['passed']}"
        )
        print(
            f"  23. nothing under the run dir holds the captured artifacts, even with "
            f"--keep-work: {len(artifacts_under_run_dir)} found under {setup_run_dir} "
            f"(store_under_run_dir="
            f"{setup_results['setup']['artifact_store_under_run_dir']})"
        )
        print(
            f"  24. and they are hash-verified anyway (the second, independent mechanism): "
            f"tampering the store from inside the tool renders the tests oracle "
            f"available={tamper_oracle['available']} passed={tamper_oracle['passed']} — "
            f"absence, never a failed candidate"
        )
        print("")
        print(
            "no model dispatched, no network, no money spent; nothing written outside "
            f"{tmp}"
        )
    return 0


# ---------------------------------------------------------------------------------------------
# CLI


def build_prefs_payload(verdict_card, pricing):
    """PLAN D9's pinned prefs schema. `verdict_card` carries `run_id`, `repo`, `tier_map`
    (T8's `{"slots": {...}, ...}` shape), `daily_driver` (T8's `{"pick": id|None, ...}`
    shape) and `labels` -- either the full `build_verdict()` card or, as `apply_verdict`
    builds it, that same shape assembled from `results.json["verdict"]` plus the envelope's
    own `run_id`/`repo`. A below-floor card never reaches this function (the caller refuses
    first); `labels` is LIFTED verbatim from the card, so an envelope-level
    `GRADING_FAILED_LABEL` / `STORE_WRITE_FAILED_LABEL` survives into the prefs file exactly
    as it read on the verdict.

    `pricing` re-canonicalizes each id through `cost_report.match_model` (the same lookup
    every other price-deriving function in this module uses) -- the caller already checked
    every id resolves against it (staleness), so this only normalizes date/`[1m]`-suffixed
    ids down to their pricing-file key, never changes what a value MEANS.
    """
    cr = _cr()

    def _canon(model_id):
        if not model_id:
            return None
        return cr.match_model(model_id, pricing) or model_id

    tier_map = verdict_card.get("tier_map") or {}
    slots = tier_map.get("slots") or {}
    daily_driver = verdict_card.get("daily_driver") or {}

    return {
        "schema_version": PREFS_SCHEMA_VERSION,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "source_run": verdict_card.get("run_id"),
        "repo": verdict_card.get("repo"),
        "tiers": {slot: _canon(slots.get(slot)) for slot in TIER_SLOTS},
        "daily_driver": _canon(daily_driver.get("pick")),
        "labels": list(verdict_card.get("labels") or []),
    }


def _validate_applied_shapes(verdict):
    """T9 defect 2: a `tier_map`/`daily_driver` that is PRESENT but not in the expected shape
    must refuse as a malformed card, never silently resolve to "nothing to validate". `None`
    is legitimate -- `build_verdict` omits either key when its `goal` excludes it (e.g. a
    daily-driver-only run has `tier_map: None`) -- but a present value that doesn't carry the
    expected keys is a corrupted/hand-edited card, not one with nothing to check. Called
    BEFORE `_apply_staleness_check` so a wrongly-shaped `tier_map` (e.g. a flat
    `{"strong": id, ...}` with no `"slots"` wrapper) can never let a stale id slip through by
    being structurally unreachable.
    """
    tier_map = verdict.get("tier_map")
    if tier_map is not None:
        if not isinstance(tier_map, dict) or not isinstance(tier_map.get("slots"), dict):
            raise ValueError(
                "verdict's tier_map is present but missing the expected 'slots' shape — "
                "malformed card, refusing to apply"
            )
        # F3 (Phase 4 review): a non-string slot value used to reach `cost_report.match_model`
        # and come back out as an AttributeError, which is NOT in `main`'s handled set -- so
        # `apply` printed a traceback where every sibling refusal prints one plain sentence.
        for slot, value in tier_map["slots"].items():
            if value is not None and not isinstance(value, str):
                raise ValueError(
                    f"verdict's tier_map slot {slot!r} holds {type(value).__name__}, not a "
                    f"model id — malformed card, refusing to apply"
                )
    daily_driver = verdict.get("daily_driver")
    if daily_driver is not None:
        if not isinstance(daily_driver, dict) or "pick" not in daily_driver:
            raise ValueError(
                "verdict's daily_driver is present but missing the expected 'pick' shape — "
                "malformed card, refusing to apply"
            )
        pick = daily_driver["pick"]
        if pick is not None and not isinstance(pick, str):
            raise ValueError(
                f"verdict's daily_driver pick holds {type(pick).__name__}, not a model id — "
                f"malformed card, refusing to apply"
            )


def _apply_staleness_check(verdict, pricing):
    """PLAN D9's staleness refusal: every populated tier slot AND the daily-driver pick must
    still resolve against the CURRENT `data/pricing.json` -- a model dropped from the roster
    since the run was measured must not silently keep routing work. Assumes
    `_validate_applied_shapes` already ran, so a present `tier_map`/`daily_driver` is
    guaranteed to carry the expected shape here."""
    cr = _cr()
    tier_map = verdict.get("tier_map") or {}
    slots = tier_map.get("slots") or {}
    daily_driver = verdict.get("daily_driver") or {}

    ids = [model_id for model_id in slots.values() if model_id]
    dd_pick = daily_driver.get("pick")
    if dd_pick:
        ids.append(dd_pick)

    for model_id in ids:
        if cr.match_model(model_id, pricing) is None:
            raise ValueError(
                f"model {model_id} is no longer in data/pricing.json — re-run the benchmark"
            )


def apply_verdict(run_dir, prefs_path, pricing):
    """PLAN D9's read + refuse + write, with no printing (the CLI wrapper owns the receipt).

    Reads the run's OWN recorded verdict -- `results.json["verdict"]`, exactly what `verdict`
    already wrote there -- and never recomputes one; `apply` must act on the same card a user
    already read, not a fresh one built from possibly-different flags. Refuses (`ValueError`,
    caught by `main`'s top-level handler into the same exit-2 path every other subcommand
    uses) when: no verdict is recorded, the recorded verdict is below the evidence floor
    (D7), or any tier/daily-driver id no longer resolves in the current pricing file
    (staleness). Otherwise writes the pinned schema ATOMICALLY (temp file + `Path.replace`,
    which is atomic on the same filesystem) and returns `(payload, old_payload)` -- the prior
    file's content (or `None`) read before the overwrite, so the CLI can print both.
    """
    run_dir = Path(run_dir)
    results_path = run_dir / "results.json"
    if not results_path.exists():
        raise FileNotFoundError(
            f"no results.json in {run_dir} — a verdict is applied from a run's envelope, "
            f"never reconstructed"
        )
    results = json.loads(results_path.read_text())
    verdict = results.get("verdict")
    if not verdict:
        raise ValueError("no verdict recorded for this run — run verdict first")
    if not isinstance(verdict, dict):
        raise ValueError(
            "verdict is not a valid record (expected an object) — malformed results.json, "
            "refusing to apply"
        )
    # T9 defect 1: the gate must fail CLOSED. `below_floor` must be AFFIRMATIVELY `False` --
    # an absent key (`.get` would silently default to `None`), `None`, a string, or any other
    # non-bool is a malformed card, not "not below the floor", and must refuse just like an
    # explicit `True` does.
    below_floor = verdict.get("below_floor")
    if below_floor is True:
        raise ValueError("a below-floor verdict is never applied")
    if below_floor is not False:
        raise ValueError(
            "verdict is missing a valid below_floor flag — malformed card, refusing to apply"
        )
    _validate_applied_shapes(verdict)
    _apply_staleness_check(verdict, pricing)

    verdict_card = dict(verdict)
    verdict_card["run_id"] = results.get("run_id")
    verdict_card["repo"] = results.get("repo")
    payload = build_prefs_payload(verdict_card, pricing)

    prefs_path = Path(prefs_path)
    old_payload = None
    if prefs_path.exists():
        try:
            old_payload = json.loads(prefs_path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            old_payload = None
    if not isinstance(old_payload, dict):
        old_payload = None

    # F3 (Phase 4 review), refusal 1 -- A PAYLOAD THAT NAMES NO MODEL IS NOT A ROUTING
    # DECISION. `build_prefs_payload` reads `slots.get(slot)`, so a card yielding zero ids
    # applied cleanly and ERASED an existing prefs file at exit 0. That is engine-producible,
    # not a hand-edit: `verdict --goal daily-driver` sets `tier_map: None`, and `_daily_driver`
    # legitimately returns `pick: None` when no candidate is eligible-and-priced.
    if not any(payload["tiers"].values()) and not payload["daily_driver"]:
        raise ValueError(
            "this verdict names no model in any tier slot and no daily driver — there is "
            "nothing to apply, and writing it would erase whatever routing state the prefs "
            "file already holds; re-run the benchmark or re-render the verdict"
        )

    # F3, refusal 2 -- A GOAL-SCOPED VERDICT NEVER CLEARS WHAT IT DID NOT MEASURE.
    # `verdict --goal daily-driver` emits `tier_map: None` (and `--goal tiers` emits
    # `daily_driver: None`): the key is absent because the goal EXCLUDED it, not because the
    # run measured nothing there. Applying such a card over a populated prefs file silently
    # blanked slots this run never looked at.
    #
    # Refuse rather than merge, and the rationale is the schema: `prefs/repo-bench.json` pins
    # exactly ONE `source_run` (D9). Carrying unmeasured slots forward from an earlier apply
    # would leave that field false for those slots -- a file whose `tiers` came from run A and
    # whose `daily_driver` came from run B, stamped with B alone. This kit's spine is that
    # every recorded value carries its true basis, and per-field provenance is a schema change
    # this task does not own. Re-render with `--goal both` and apply that instead.
    if old_payload:
        scoped_conflicts = []
        if verdict.get("tier_map") is None and any((old_payload.get("tiers") or {}).values()):
            scoped_conflicts.append("tiers")
        if verdict.get("daily_driver") is None and old_payload.get("daily_driver"):
            scoped_conflicts.append("daily_driver")
        if scoped_conflicts:
            raise ValueError(
                f"this verdict was rendered with goal {verdict.get('goal')!r}, so it never "
                f"measured {', '.join(scoped_conflicts)} — applying it would blank the "
                f"{', '.join(scoped_conflicts)} already in {prefs_path} with values from a run "
                f"that did not measure them, and the prefs schema records only ONE source_run, "
                f"so a merge could not say where each value came from; re-render this run's "
                f"verdict with --goal both and apply that"
            )

    prefs_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = prefs_path.with_name(prefs_path.name + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2) + "\n")
    tmp_path.replace(prefs_path)

    return payload, old_payload


def cmd_apply(args):
    """`apply` is the ONLY routing-state writer (D9): running it IS the explicit opt-in, so
    there is no `--yes` -- the printed receipt below is what makes the write informed, not a
    confirmation prompt."""
    store_dir = Path(args.store_dir) if args.store_dir else DEFAULT_STORE_DIR
    run_dir = store_dir / args.run
    if not run_dir.is_dir():
        raise FileNotFoundError(
            f"no run {args.run!r} in the benchruns store at {store_dir} — `list` shows what "
            f"is there"
        )
    prefs_path = Path(args.prefs_path) if args.prefs_path else DEFAULT_PREFS_PATH
    pricing = _cr().load_pricing()

    payload, old_payload = apply_verdict(run_dir, prefs_path, pricing)

    print(f"applying verdict from run {payload['source_run']} (repo: {payload['repo']}):")
    if old_payload:
        print(f"  old tiers:        {old_payload.get('tiers')}")
        print(f"  old daily_driver: {old_payload.get('daily_driver')}")
    else:
        print(f"  no existing prefs file at {prefs_path}")
    print(f"  new tiers:        {payload['tiers']}")
    print(f"  new daily_driver: {payload['daily_driver']}")
    print(f"wrote {prefs_path}")
    return 0


def _read_prefs_source_run(prefs_path):
    """Tolerant single-file read for `list`'s applied-marker column -- absence or a broken
    file is `None`, never a crash (the same tolerance PLAN D8 requires of the run store
    applies to reading the ONE prefs file, too)."""
    prefs_path = Path(prefs_path)
    if not prefs_path.exists():
        return None
    try:
        data = json.loads(prefs_path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None
    return data.get("source_run") if isinstance(data, dict) else None


def _format_spend_cell(spend):
    """No dollars invented for a run without a spend record (T9): `-`, never `$0.0000`."""
    if not spend or spend.get("spent_usd") is None:
        return NA
    return f"${spend['spent_usd']:.4f} ({spend.get('basis', '?')})"


def cmd_list(args):
    store_dir = Path(args.store_dir) if args.store_dir else DEFAULT_STORE_DIR
    rows, notes = list_runs(store_dir)

    prefs_path = Path(args.prefs_path) if args.prefs_path else DEFAULT_PREFS_PATH
    applied_source_run = _read_prefs_source_run(prefs_path)
    for row in rows:
        row["applied"] = bool(applied_source_run) and row.get("run_id") == applied_source_run

    if args.json:
        print(json.dumps({"store_dir": str(store_dir), "runs": rows, "notes": notes}, indent=2))
        return 0

    print(f"benchruns store: {store_dir}")
    for row in rows:
        print(
            f"  {row.get('run_id', '?')}   created {row.get('created_at', 'unknown')}"
            f"   schema {row.get('store_schema_version', '?')}"
        )
        print(
            f"      repo: {row.get('repo') or NA}   mode: {row.get('mode') or NA}"
            f"   candidates: {', '.join(row['candidates']) if row.get('candidates') else NA}"
        )
        below_floor = row.get("below_floor")
        below_floor_text = NA if below_floor is None else ("yes" if below_floor else "no")
        print(
            f"      spend: {_format_spend_cell(row.get('spend'))}"
            f"   verdict: {'yes' if row.get('verdict_present') else 'no'}"
            f"   below-floor: {below_floor_text}"
            f"   applied: {'yes' if row['applied'] else 'no'}"
        )
    for note in notes:
        print(f"  note: {note}")
    return 0


def _add_mining_args(parser):
    """Flags shared by `plan` and `run` -- everything `build_plan` needs except pricing and
    a scratch dir (those are wired by each command, since only `run` ever has a run dir)."""
    parser.add_argument("--repo", required=True, help="target repo path (read-only)")
    parser.add_argument(
        "--models", required=True, help="comma-separated candidate model ids or tier words"
    )
    parser.add_argument(
        "--mode", default="auto", choices=("auto", "issue-replay", "general"),
        help="acquisition mode (default: auto -- PLAN D4)",
    )
    parser.add_argument("--limit", type=int, default=8, help="max tasks to mine (default: 8)")
    parser.add_argument(
        "--test-cmd", default=None,
        help="test command for general mode (PLAN D4/D11 -- runs only in a sandbox)",
    )
    parser.add_argument(
        "--setup-cmd", default=None,
        help=(
            "command run ONCE per grade template, inside a sandbox, before --test-cmd — for "
            "targets that must install or compile before their tests can run (T17). Opt-in "
            "and never invented; it carries the same arbitrary-code exposure as --test-cmd "
            "(PLAN D11), and it never runs in a candidate's sandbox, during `plan`, or "
            "without --test-cmd. A setup failure makes the tests oracle UNAVAILABLE for every "
            "grading that depended on it — never a failed cell."
        ),
    )
    parser.add_argument(
        "--setup-key", action="append", default=None,
        help=(
            "repo-relative path (repeatable) whose content at a task's base commit keys its "
            "grade template, e.g. --setup-key package-lock.json (T17). Tasks whose keyed "
            "content matches share ONE prepared template instead of one per base commit. "
            "Without it, templates are keyed on the base commit."
        ),
    )
    parser.add_argument("--judge", default=None, help="judge model id or tier (default: PLAN D6)")
    parser.add_argument("--commit", default=None, help="base commit (default: rev-parse HEAD)")
    parser.add_argument(
        "--exclude-subject", action="append", default=None,
        help=(
            "regex (repeatable), matched case-insensitively against a mined commit's "
            "subject line -- drop it from the mined task set (opt-in; no pattern excludes "
            "nothing, T13)"
        ),
    )
    parser.add_argument(
        "--with-gh", action="store_true",
        help=(
            "enrich issue-replay statements with the real issue title/body via "
            "`gh api repos/<owner>/<name>/issues/<N>` (requires gh installed and "
            "authenticated; one API call per issue-referencing task). Opt-in mitigation for "
            "squash-merge repos where the commit message describes the fix, not the bug "
            "(T14) -- any failure degrades to the commit-message statement, labelled and "
            "noted, never invented. A number that resolves to a pull request (very common: "
            "`(#N)` squash subjects are PR numbers) never contributes its body -- it "
            "explains the fix, which is a worse leak than the commit message (T16). "
            "REQUIRES --gh-repo (T15): `gh` resolves the repository from the current "
            "working directory, not from --repo, so an unset --gh-repo would silently "
            "query the wrong project."
        ),
    )
    parser.add_argument(
        "--gh-repo", default=None,
        help=(
            "OWNER/NAME of the GitHub repository to query with --with-gh (required whenever "
            "--with-gh is set; T15). NEVER inferred from --repo's origin remote: that would "
            "be wrong for a fork, whose issues live upstream, not at the fork's own remote."
        ),
    )


def cmd_plan(args):
    pricing = _cr().load_pricing()
    models = _split_models(args.models)
    # T15: refuse BEFORE any mining starts -- a silent wrong-repo `gh` lookup reads exactly
    # like a real measurement, so this is a hard gate, not a degradation.
    use_gh, gh_repo = _resolve_gh_repo(args)
    # T14: the real subprocess `gh` runner is constructed HERE, on the CLI `--with-gh` path
    # only -- `build_plan`/`mine_issue_tasks` keep `gh_runner=None` as their own default,
    # unchanged, so no import or unset invocation can ever reach a real `gh`.
    gh_runner_arg = None
    if use_gh:
        gh_runner_arg = default_gh_runner
    # T18: read-only against the store, and deliberately OPT-IN -- unlike `run`/`list`/
    # `verdict`/`apply`, `plan` has never touched a store (D1: it is pure mining + pricing),
    # and it must not start silently reading `DEFAULT_STORE_DIR` just because this feature
    # landed: that would make a bare `plan` invocation depend on whatever this machine's real
    # benchruns/ happens to hold. Omitting `--store-dir` means "no calibration data" honestly
    # -- it never falls back to the real store the way `run` does.
    calibration_store_dir = Path(args.store_dir) if getattr(args, "store_dir", None) else None
    with tempfile.TemporaryDirectory(prefix="repo-bench-plan-") as tmp:
        card = build_plan(
            target_repo=args.repo, models=models, mode=args.mode, limit=args.limit,
            test_cmd=args.test_cmd, judge=args.judge, pricing=pricing, commit=args.commit,
            scratch_dir=Path(tmp) / "work",
            exclude_subject=tuple(args.exclude_subject or ()),
            use_gh=use_gh, gh_runner=gh_runner_arg, gh_repo=gh_repo,
            setup_cmd=getattr(args, "setup_cmd", None), store_dir=calibration_store_dir,
        )
    if args.json:
        print(json.dumps(card, indent=2))
    else:
        print(render_plan_markdown(card))
    return 0


def cmd_run(args, runner=None, adapter=None, git_runner=None, test_runner=None):
    """PLAN D1's structural refusal, then the live dispatch loop.

    A plan is always built first (mining happens either way, so the refusal path can print the
    SAME card `plan` would) -- through `<run-dir>/work` as the general-mode scratch dir (F11b),
    never a system temp dir. The run dir is removed again on either refusal path (missing
    flags, or over ceiling): PLAN D1 says a runaway benchmark must be structurally hard, and
    that includes never leaving a trace of a run that never happened in the store.

    Past the gate, every cell is: ceiling-checked FIRST (`would_exceed_ceiling`, which
    re-validates the ceiling every time), then given a fresh sandbox under `<run-dir>/work`,
    then dispatched through `runner` -- injectable, which is how every test drives this loop
    without a binary, a network, or a cent. Crossing the ceiling stops the WHOLE run cleanly
    (exit 0, stated on stdout): remaining cells are recorded `skipped: cost-ceiling` and the
    envelope is labelled `partial (cost-ceiling)`. A stop is an outcome, not an error.

    THE RUN DIR HOLDS NO SOLUTION MATERIAL WHILE A DISPATCH IS LIVE (F1). A candidate runs with
    `cwd=<run-dir>/work/cell-NNN` and permissions bypassed, so everything above that directory
    is one `cat` away: `tasks/<id>.json` (reference patch AND withheld test blobs, both modes),
    `dispatches/*.json` (an earlier candidate's captured patch), `plan.json` (whose
    general-mode task ids, `mut-N-<stem>`, name the mutated file), a setup patch, a mining
    scratch sandbox. PLAN D3's "unreachable by construction" was true of git HISTORY and false
    of the filesystem. So the plan card, the task records and the dispatch records are all
    buffered in memory and written only once EVERY dispatch -- candidate AND judge -- has
    returned (nothing reads them from disk before then; grading works from the in-memory task
    records); setup patches never touch the run dir; mining sandboxes die with their red check;
    and each cell sandbox is swept the moment its patch is captured. The candidate sandboxes
    stay UNDER the run dir -- moving them out would make PLAN D3/D11's "all mutation happens
    under the run dir" false, which is the wrong trade. The JUDGE's cwd is the one dispatch
    that deliberately lives outside it (F1, Phase 3 review -- see `oracle_judge`): it is not a
    candidate sandbox and mutates no target, and anchoring it under the run dir put
    `../../tasks/<id>.json` and `../../dispatches/<id>__<model>.json` one `cat` away from the
    dispatch that must not learn which patch is the reference, or whose the other one is.
    """
    store_dir = Path(args.store_dir) if args.store_dir else DEFAULT_STORE_DIR
    adapter = adapter or CLAUDE_ADAPTER
    pricing = adapter["load_pricing"]()
    models = _split_models(args.models)
    claude_bin = getattr(args, "claude_bin", None) or DEFAULT_CLAUDE_BIN
    keep_work = bool(getattr(args, "keep_work", False))

    # Ceiling validation happens BEFORE the structural check and BEFORE any run dir is
    # created (GUARDRAILS: "the ceiling is re-checked before EVERY dispatch" -- a malformed
    # ceiling must never even reach the "both flags present" gate, let alone the spend
    # comparison, and a refused run must leave no trace in the store).
    try:
        max_usd = validate_ceiling(args.max_usd)
    except ValueError as e:
        print(f"refusing to dispatch: {e}", file=sys.stderr)
        sys.exit(2)

    # T15: same "refuse before any mining starts" posture as the ceiling check above -- a
    # malformed --gh-repo, or --with-gh with none, must never even reach a run dir.
    try:
        use_gh, gh_repo = _resolve_gh_repo(args)
    except ValueError as e:
        print(f"refusing to dispatch: {e}", file=sys.stderr)
        sys.exit(2)

    live = bool(args.live)

    # T14: same posture as `cmd_plan` -- the real subprocess `gh` runner is constructed HERE,
    # on the CLI `--with-gh` path only; `build_plan`/`mine_issue_tasks` keep `gh_runner=None`
    # as their own default, unchanged.
    gh_runner_arg = None
    if use_gh:
        gh_runner_arg = default_gh_runner
    run_id, run_path = new_run_dir(store_dir)
    tasks = []
    try:
        card = build_plan(
            target_repo=args.repo, models=models, mode=args.mode, limit=args.limit,
            test_cmd=args.test_cmd, judge=args.judge, pricing=pricing, commit=args.commit,
            scratch_dir=run_path / "work", git_runner=git_runner, test_runner=test_runner,
            tasks_out=tasks, exclude_subject=tuple(args.exclude_subject or ()),
            use_gh=use_gh, gh_runner=gh_runner_arg, gh_repo=gh_repo,
            setup_cmd=getattr(args, "setup_cmd", None),
            # T18: `run`'s refusal-path plan print goes through the SAME card as `plan`
            # (module docstring above) -- `store_dir` is already resolved above and every
            # existing `run` test already supplies it explicitly (D8: `run` always writes
            # somewhere), so this never touches a real store `run`'s own tests didn't ask for.
            store_dir=store_dir,
        )
    except Exception:
        shutil.rmtree(run_path, ignore_errors=True)
        raise

    if not (live and max_usd is not None):
        print(render_plan_markdown(card))
        print(
            "refusing to dispatch: run requires --live AND --max-usd <ceiling>",
            file=sys.stderr,
        )
        shutil.rmtree(run_path, ignore_errors=True)
        sys.exit(2)

    grand_total = card["totals"]["grand_total"]
    if grand_total > max_usd:
        print(render_plan_markdown(card))
        print(
            f"planned estimate ${grand_total:.4f} exceeds --max-usd ${max_usd:.4f} -- raise "
            f"the ceiling or shrink the matrix",
            file=sys.stderr,
        )
        shutil.rmtree(run_path, ignore_errors=True)
        sys.exit(2)

    # T5R2: `plan.json` names every task, and a general-mode task id is `mut-N-<stem>` --
    # `cat ../../plan.json` from a candidate's cwd narrows the hunt to ONE file even with
    # every other ancestry fix in place. It gets the same treatment T5R gave `tasks/` and
    # `dispatches/`: buffered and written after the last dispatch returns. When NOTHING will
    # be dispatched there is no candidate to leak to, so it is written immediately and the
    # run dir looks exactly as it does today (T4's plan-recorded path).
    will_dispatch = bool(tasks) and bool(card["candidates"])
    if not will_dispatch:
        (run_path / "plan.json").write_text(json.dumps(card, indent=2) + "\n")
    print(render_plan_markdown(card))
    print("")

    work_dir = run_path / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    # T17: the `--setup-cmd` template cache, constructed ONLY when the flag was given -- with no
    # flag `templates` stays None all the way down and every grading path is byte-for-byte what
    # it was before this feature existed. Its BUILD area is under `work/` (PLAN D3/D11:
    # arbitrary setup code runs under the run dir, never a system temp dir) and is swept with
    # the rest of `work/`; its CAPTURED ARTIFACTS are held outside the run dir entirely and are
    # deleted by `templates.cleanup()` in the `finally` below (T17R/F1 -- everything under the
    # run dir is one `../..` from a candidate's cwd, for the whole run). It is passed to the
    # GRADING paths only; a candidate's own sandbox (`prepare_cell_sandbox` in the loop below)
    # never gets one.
    setup_cmd = getattr(args, "setup_cmd", None)
    templates = None
    templates_root = work_dir / "templates"
    if setup_cmd:
        templates = GradeTemplates(
            card["repo"], templates_root, setup_cmd, test_runner=test_runner,
            git_runner=git_runner, key_paths=tuple(getattr(args, "setup_key", None) or ()),
        )

    cells = []
    notes = list(card["notes"])
    labels = list(card["labels"])
    spent_usd = 0.0
    stopped = False
    completed = False
    overspent = False
    cell_n = 0
    results_path = run_path / "results.json"
    #: T6/D5's red-check cache -- ONE `oracle_tests_red_check` call per task per run, reused
    #: across every candidate cell for that task (the outer loop over `tasks` naturally makes
    #: this "once per task"; the dict guards it explicitly rather than relying on that shape).
    red_check_cache = {}

    if keep_work:
        print(KEEP_WORK_WARNING)
        print("")
        notes.append(KEEP_WORK_WARNING)

    #: F1: buffered for the WHOLE loop AND the whole grading pass, written only once the last
    #: dispatch of either kind has returned. `tasks/<id>.json` carries `reference_patch` and
    #: `test_blobs` and sits two `../`s from a candidate's cwd;
    #: `dispatches/<id>__<model>.json` carries an earlier candidate's captured patch (and
    #: names the MODEL that wrote it) one `../` away; `plan.json` (T5R2) names the tasks.
    #: Nothing reads any of them from disk -- grading takes the in-memory records.
    pending_writes = [(Path("plan.json"), card)] if will_dispatch else []

    try:
        for task in tasks:
            for cid in card["candidates"]:
                estimate = estimate_dispatch_usd(cid, task["size_profile"], pricing)

                # CEILING FIRST -- before the sandbox, before the argv, before anything that
                # could cost a cent (PLAN D1). `would_exceed_ceiling` re-validates the ceiling.
                if not stopped and would_exceed_ceiling(spent_usd, estimate, max_usd):
                    stopped = True
                    notes.append(
                        f"cost ceiling reached before dispatching {task['task_id']} x {cid}: "
                        f"recorded spend ${spent_usd:.4f} + this cell's estimate "
                        f"${estimate:.4f} exceeds --max-usd ${max_usd:.4f} — the run stopped "
                        f"there"
                    )
                if stopped:
                    cells.append(_skipped_cell(task["task_id"], cid, estimate))
                    continue

                cell_n += 1
                info, baseline = prepare_cell_sandbox(
                    task, card["repo"], work_dir / f"cell-{cell_n:03d}", git_runner=git_runner,
                )
                record = dispatch_cell(
                    task, cid, adapter, info["path"], runner=runner, claude_bin=claude_bin,
                    pricing=pricing, estimated_usd=estimate, baseline_commit=baseline,
                    git_runner=git_runner,
                )
                pending_writes.append(
                    (Path("dispatches") / f"{task['task_id']}__{cid}.json", record)
                )
                spent_usd += record["usd"] or 0.0

                # T6/D5: graded AFTER patch capture (`record["patch"]` above), while
                # `info["path"]` -- the candidate's OWN sandbox -- still exists and BEFORE it
                # is swept. Both oracles read `info["path"]`/`record["patch"]` only; neither
                # ever writes into the candidate's sandbox (THE LEAK RULE).
                #
                # Nit (Phase 3 review): the RED CHECK RUNS FIRST. It used to run second, so a
                # task the check then demoted had already executed the target's arbitrary test
                # command once per cell -- D11 exposure bought for a grade that was thrown
                # away. A demoted task's tests oracle is now built from the demotion alone
                # (`rc: None`, not a stale `rc: 0` from a run whose result nobody may read).
                if task["task_id"] not in red_check_cache:
                    red_check_cache[task["task_id"]] = oracle_tests_red_check(
                        task, card["repo"], args.test_cmd, test_runner, work_dir,
                        git_runner=git_runner, templates=templates,
                    )
                red_check = red_check_cache[task["task_id"]]
                if red_check and red_check.get("passed_at_base"):
                    tests_oracle = {
                        "oracle": "tests", "available": False, "passed": None, "rc": None,
                        "notes": TESTS_NOT_DISCRIMINATING_NOTE,
                        # Demoted before grading, so no substrate was ever constructed (F1)
                        # and no scope split was ever taken -- `None`, not `[]`.
                        "out_of_scope": None,
                    }
                else:
                    # F1: the CANDIDATE'S PATCH, not its sandbox. The tree the candidate wrote
                    # is not an input to the grade -- `oracle_tests` builds its own substrate
                    # from the task's base state plus the in-scope slice of this patch.
                    tests_oracle = oracle_tests(
                        task, record["patch"], args.test_cmd, test_runner, work_dir,
                        target_repo=card["repo"], git_runner=git_runner, templates=templates,
                    )
                structural_oracle = oracle_structural(task["reference_patch"], record["patch"])

                cell = dict(record)
                cell["estimated_usd"] = estimate
                cell["skipped"] = None
                cell["oracles"] = {"tests": tests_oracle, "structural": structural_oracle}
                # F2: visible, never punitive -- the test surface was restored from base
                # before grading, so this could not have earned a `solved`; T8 still gets to
                # see that the candidate went there.
                touched_tests = _touched_test_paths(record["patch"])
                cell["candidate_touched_tests"] = touched_tests
                if touched_tests:
                    notes.append(
                        f"{task['task_id']} x {cid}: {CANDIDATE_TOUCHED_TESTS_NOTE} "
                        f"({', '.join(touched_tests)})"
                    )
                # F1: the scope split's own record, surfaced exactly the way the test-edit
                # record is. These paths reach the verdict and nothing else -- they were never
                # applied to the substrate. The tradeoff that buys is a FALSE NEGATIVE (see
                # CANDIDATE_OUT_OF_SCOPE_NOTE) and the whole point of carrying the paths up
                # here is that a reader can tell that story apart from "the model failed".
                out_of_scope = tests_oracle.get("out_of_scope")
                cell["candidate_modified_out_of_scope"] = out_of_scope
                if out_of_scope:
                    notes.append(
                        f"{task['task_id']} x {cid}: {CANDIDATE_OUT_OF_SCOPE_NOTE} "
                        f"({', '.join(out_of_scope)})"
                    )
                cells.append(cell)

                # Swept the moment its patch is captured (F1): a kept sandbox is an earlier
                # candidate's work sitting one `../` from the next candidate's cwd.
                if not keep_work:
                    shutil.rmtree(info["path"], ignore_errors=True)
        completed = True
    finally:
        # F6 (Phase 2) / F3 (Phase 3): the envelope is written from here, ALWAYS, and it is
        # written LAST. Anything raising inside the loop used to skip this write entirely,
        # leaving a run with no results.json -- no spend, no basis, no labels -- which is
        # precisely the one artifact PLAN D8 says must always carry them. T7 then reopened the
        # same hole from above by adding a SPENDING step (judge grading) between the `finally`
        # and the write: a judge dispatch that raised -- a vanished binary, a pricing failure,
        # a temp-dir failure -- destroyed the envelope after real candidate money had already
        # been spent. Every step below that can raise is guarded and degrades to a note plus a
        # label; nothing between here and `results_path.write_text` may abort it.

        # PLAN D6's judge grades, dispatched here through the SAME ceiling check every
        # candidate dispatch uses (P2-F5): `grade_cells` takes `spent_usd`/`max_usd` IN and
        # hands back the updated `spent_usd` OUT, so judge dollars land in `spend.spent_usd`
        # and `_spend_basis` below sees them too. Only attempted when the dispatch loop
        # actually completed -- an aborted run (the `except` path re-raising through this
        # `finally`) must not spend further while it is already unwinding from a failure.
        #
        # F1 (Phase 3): grading runs BEFORE the store writes below, so `tasks/`,
        # `dispatches/` and `plan.json` are still unwritten while the judge is dispatching --
        # the second leg of keeping the answer key (and the candidate's model id) out of any
        # dispatch's filesystem ancestry.
        grades = []
        if completed:
            spent_before_grading = spent_usd
            try:
                grades, spent_usd, judge_stopped = grade_cells(
                    cells, tasks, card["judge"], adapter, runner, claude_bin, pricing,
                    spent_usd, max_usd, grades_out=grades,
                )
            except Exception as e:  # noqa: BLE001 -- a grading failure must not cost the envelope
                judge_stopped = False
                # Grades produced before the raise are already in `grades` (that is what
                # `grades_out` is for), so their dollars are recovered rather than lost: an
                # envelope that under-reports spend is the same dishonesty as no envelope.
                spent_usd = spent_before_grading + sum((g.get("usd") or 0.0) for g in grades)
                labels.append(GRADING_FAILED_LABEL)
                notes.append(f"{GRADING_FAILED_NOTE}: {type(e).__name__}: {e}")
            if judge_stopped:
                stopped = True
                notes.append(
                    f"cost ceiling reached before grading every cell: recorded spend "
                    f"${spent_usd:.4f} against a ${max_usd:.4f} ceiling — remaining judge "
                    f"grades were skipped (skipped: cost-ceiling)"
                )
        else:
            notes.append(
                "judge grading was not attempted — the dispatch loop aborted before "
                "completing"
            )

        # No dispatch of any kind is live past this point, so the mined records (reference
        # patch + test blobs included) and the per-cell dispatch records land in the STORE
        # now: never in a prompt, never in a candidate's sandbox, and never in the run dir
        # while a candidate OR a judge could read them.
        try:
            for task in tasks:
                (run_path / "tasks" / f"{task['task_id']}.json").write_text(
                    json.dumps(task, indent=2) + "\n"
                )
            for rel_path, record in pending_writes:
                (run_path / rel_path).write_text(json.dumps(record, indent=2) + "\n")
        except Exception as e:  # noqa: BLE001 -- same rule: the envelope outranks its siblings
            labels.append(STORE_WRITE_FAILED_LABEL)
            notes.append(f"{STORE_WRITE_FAILED_NOTE}: {type(e).__name__}: {e}")

        # T17: the template accounting. A cache that silently misses is indistinguishable from
        # no cache, so the prepared/served counts ride in the envelope AND on the terminal line.
        # `setup_seconds` is deliberately its OWN number: template preparation is toolchain
        # time, and folding it into a cell's `wall_seconds` would charge whichever model
        # happened to be graded first for the target's build -- oracle (d) is what the
        # daily-driver pick reads.
        setup_report = templates.report() if templates is not None else None
        if setup_report is not None:
            if setup_report["templates_failed"]:
                labels.append(SETUP_FAILED_LABEL)
                for entry in setup_report["templates"]:
                    if not entry["ok"]:
                        notes.append(
                            f"grade template {entry['key']} "
                            f"({'; '.join(entry['key_basis'])}) for task(s) "
                            f"{', '.join(entry['task_ids']) or '(none)'}: {entry['note']}"
                        )
            # T17R/F1: a store that failed verification is a run-level honesty event, labelled
            # like a setup failure and for the same reason -- the gradings that depended on it
            # rendered n/a, and a reader must not have to infer that from a cell.
            if setup_report["artifacts_tampered"]:
                labels.append(ARTIFACT_TAMPERED_LABEL)
                notes.append(
                    f"{ARTIFACT_TAMPERED_NOTE} "
                    f"({', '.join(setup_report['artifacts_tampered'])})"
                )
            # T17R/F2+F7: every refused share, every verified one, and every absent key path.
            notes.extend(setup_report["sharing_notes"])
            if setup_report["key_paths_absent"]:
                labels.append(SETUP_KEY_ABSENT_LABEL)
            notes.append(
                f"--setup-cmd: {setup_report['templates_prepared']} grade template(s) prepared "
                f"({setup_report['templates_failed']} failed) and reused across "
                f"{setup_report['gradings_served']} grading(s); "
                f"{setup_report['setup_seconds']:.3f}s of setup time, which is toolchain time "
                f"and is never part of any cell's wall_seconds"
            )
            notes.append(ARTIFACT_STORE_NOTE)
            # The captured artifacts go, always: they live outside the run dir, so `--keep-work`
            # (which preserves the run's own working area) has nothing to say about them.
            templates.cleanup()
            if not keep_work:
                shutil.rmtree(templates_root, ignore_errors=True)

        basis = _spend_basis(cells, grades)
        labels.append(SPEND_BASIS_LABELS[basis])
        if stopped:
            labels.append(COST_CEILING_LABEL)
        # F3: an overshoot is unavoidable (a dispatch's cost is unknown until it returns) but
        # it is never unlabelled -- and it is checked independently of `stopped`, because the
        # LAST cell of a completed run can cross the ceiling with no next dispatch to stop.
        overspent = max_usd is not None and spent_usd > max_usd
        if overspent:
            labels.append(_overspend_label(spent_usd, max_usd))
        if not completed:
            labels.append(ABORTED_LABEL)
            notes.append(ABORTED_NOTE)

        results = {
            "store_schema_version": STORE_SCHEMA_VERSION,
            "run_id": run_id,
            "repo": str(card["repo"]),
            "base_commit": card["base_commit"],
            "mode": card["mode"],
            "harness": adapter["name"],
            "candidates": list(card["candidates"]),
            "judge": card["judge"],
            "cells": cells,
            "grades": grades,
            "spend": {
                "ceiling_usd": max_usd,
                "spent_usd": spent_usd,
                "basis": basis,
            },
            "labels": labels,
            "notes": notes,
        }
        # Present ONLY when `--setup-cmd` was supplied: a run without the flag must be
        # byte-identical to a run before this feature existed, envelope included.
        if setup_report is not None:
            results["setup"] = setup_report
        results_path.write_text(json.dumps(results, indent=2) + "\n")

    dispatched = sum(1 for c in cells if not c.get("skipped"))
    skipped = len(cells) - dispatched
    # F5 (Phase 3 review): these counters count CELLS, and a ceiling that bit only during the
    # judge pass therefore printed "0 skipped" on the very line announcing the stop -- the
    # envelope was honest, the terminal line was not. Grades are counted here too, and only
    # the cost-ceiling ones (an `empty-reference` grade was never a budget casualty).
    grades_dispatched = sum(1 for g in grades if not g.get("skipped"))
    grades_skipped = sum(1 for g in grades if g.get("skipped") == SKIPPED_COST_CEILING)
    if stopped:
        print(
            f"STOPPED: cost ceiling reached — ${spent_usd:.4f} recorded against a "
            f"${max_usd:.4f} ceiling ({SPEND_BASIS_LABELS[basis]}); {dispatched} cell(s) "
            f"dispatched, {skipped} skipped; {grades_dispatched} judge grade(s) dispatched, "
            f"{grades_skipped} skipped ({SKIPPED_COST_CEILING}). Results labelled "
            f"{COST_CEILING_LABEL}."
        )
    else:
        print(
            f"completed: {dispatched} cell(s) dispatched, {skipped} skipped; recorded spend "
            f"${spent_usd:.4f} of a ${max_usd:.4f} ceiling ({SPEND_BASIS_LABELS[basis]})"
        )
    if overspent:
        print(_overspend_label(spent_usd, max_usd))
    if setup_report is not None:
        print(
            f"grade templates: {setup_report['templates_prepared']} prepared "
            f"({setup_report['templates_failed']} failed), reused across "
            f"{setup_report['gradings_served']} grading(s); "
            f"{setup_report['setup_seconds']:.3f}s of --setup-cmd time (toolchain time — not "
            f"in any cell's wall_seconds)"
        )
    print(f"results.json: {results_path}")
    return 0


def build_parser():
    ap = argparse.ArgumentParser(
        prog="repo_bench.py",
        description=(
            "Measure candidate Claude models on a repo's own work. Plan-first: `run` spends "
            "only behind --live AND --max-usd; target repos are read-only by construction."
        ),
    )
    sub = ap.add_subparsers(dest="command")

    p_plan = sub.add_parser("plan", help="price the models x tasks matrix and stop (no spend)")
    _add_mining_args(p_plan)
    p_plan.add_argument(
        "--store-dir", default=None,
        help=(
            "T18: store to read prior runs' actuals FROM, for the calibration line (how "
            "wrong task_profiles estimates have measured before) -- read-only, `plan` never "
            "writes here. Point it at the same store your `run`s use. Omitted means no "
            "calibration data is available, printed as such -- `plan` never falls back to "
            "the default benchruns/ the way `run`/`list`/`verdict`/`apply` do."
        ),
    )
    p_plan.add_argument("--json", action="store_true", help="machine-readable output")
    p_plan.set_defaults(func=cmd_plan)

    p_run = sub.add_parser("run", help="execute a planned matrix (requires --live and --max-usd)")
    _add_mining_args(p_run)
    p_run.add_argument("--store-dir", default=None, help="store root (default: ./benchruns)")
    p_run.add_argument("--live", action="store_true", help="required, with --max-usd, to spend")
    p_run.add_argument("--max-usd", type=float, default=None, help="hard ceiling in USD")
    p_run.add_argument(
        "--claude-bin", default=DEFAULT_CLAUDE_BIN,
        help="harness binary to dispatch (mirrors claude_execute; point it at a stub to test)",
    )
    p_run.add_argument(
        "--keep-work", action="store_true",
        help="keep each cell's sandbox under <run-dir>/work instead of deleting it",
    )
    p_run.set_defaults(func=cmd_run)

    p_verdict = sub.add_parser("verdict", help="render a run's verdict card")
    p_verdict.add_argument("--run", required=True, help="run id (see `list`)")
    p_verdict.add_argument("--store-dir", default=None, help="store root (default: ./benchruns)")
    p_verdict.add_argument(
        "--goal", default="both", choices=VERDICT_GOALS,
        help="tiers (strong/mid/weak map), daily-driver, or both (default)",
    )
    p_verdict.add_argument(
        "--min-tasks", type=int, default=None,
        help=(
            f"raise the evidence floor (PLAN D7 -- it can only RAISE; the structural floor "
            f"is {MIN_EVIDENCE_TASKS})"
        ),
    )
    p_verdict.add_argument(
        "--benchmarks", default=None,
        help=(
            "published-index file for the D10 published leg (default: bench_routing's own "
            "benchmarks path)"
        ),
    )
    p_verdict.add_argument(
        "--kits-dir", default=None,
        help="kit ledger for the D10 observed leg (default: <target repo>/.claude/kits if present)",
    )
    p_verdict.add_argument("--json", action="store_true", help="machine-readable output")
    p_verdict.set_defaults(func=cmd_verdict)

    p_apply = sub.add_parser("apply", help="write a verdict's tier map to prefs (opt-in)")
    p_apply.add_argument("--run", required=True, help="run id (see `list`)")
    p_apply.add_argument("--store-dir", default=None, help="store root (default: ./benchruns)")
    p_apply.add_argument(
        "--prefs-path", default=None,
        help="prefs file to write (default: prefs/repo-bench.json)",
    )
    p_apply.set_defaults(func=cmd_apply)

    p_list = sub.add_parser("list", help="enumerate the benchruns store (tolerant)")
    p_list.add_argument("--store-dir", default=None, help="store root (default: ./benchruns)")
    p_list.add_argument(
        "--prefs-path", default=None,
        help="prefs file to check for an applied marker (default: prefs/repo-bench.json)",
    )
    p_list.add_argument("--json", action="store_true", help="machine-readable output")
    p_list.set_defaults(func=cmd_list)

    p_demo = sub.add_parser(
        "demo", help="synthetic sandbox + patch-capture smoke (no model, no network, no money)"
    )
    p_demo.set_defaults(func=cmd_demo)

    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        sys.exit(2)
    try:
        args.func(args)
    except (ValueError, FileNotFoundError, KeyError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
