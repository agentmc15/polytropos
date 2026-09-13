#!/usr/bin/env python3
"""Artifact-aware scheduling and opt-in bounded concurrency for execution kits (step 24).

    kit_scheduler.py plan    --kit DIR [--max-parallel N] [--attempt-store DIR] [--json]
    kit_scheduler.py run     --kit DIR --harness stub|cursor [--max-parallel N] [--dry-run] ...
    kit_scheduler.py demo

SEQUENTIAL IS THE DEFAULT. `--max-parallel 1` is what every driver already does: one task,
one dispatch, one verification. Anything above one is an explicit opt-in, and what it buys is
bounded by what this file can actually enforce:

  isolation     each concurrent task runs in its OWN COPY of the workspace tree (under the
                attempt store, outside the tree), so two workers cannot write the same file
                while they run. A worker's tree is what it changed; nothing else is read from it.
  claims        every task in a batch is claimed atomically (step 16's `O_EXCL` claim) before
                anything is dispatched, and ONE admission decision covers the batch: the
                PLAN.md budget is drawn down grant by grant, so a batch of four with one
                dispatch left dispatches one and records the stop for the rest.
  write sets    what each worker changed is measured (file hashes before and after), never
                declared. `independent: yes` and a code graph with no edge between two tasks
                are hints; they prove nothing about writes and are not consulted here.
  integration   a central step reads the MANIFEST (artifact paths, verdicts, bounded
                diagnostics -- never a worker's transcript) and applies each write set to the
                main workspace in batch order. A file two workers changed, or one the user
                changed while the batch ran, is a CONFLICT: that task's tree is kept in place,
                nothing of it is applied, nothing is reset, and the task is blocked with the
                files named. Merging is explicit work, not an automatic guess.
  fresh check   every integrated task's verify command runs AGAIN on the merged tree. A check
                that passed in a worker's copy is evidence about that copy; the merged tree is
                the tree the kit is about.
  invalidation  an acceptance records the upstream artifact versions it rested on (step 24 in
                `kit_contract`); a dependency re-accepted with a different artifact makes the
                downstream acceptance stale, and stale tasks' dependents are not scheduled.

WHAT A WORKER MAY NOT DO. Edit the kit (`.claude/kits/<slug>/*` in its copy): that is
coordinator state, and a write set touching it is recorded as `security.violation` and never
integrated. Grant itself budget or capabilities: admission is decided here, before dispatch,
from PLAN.md and the ledger. Change acceptance: a plan-revision proposal
(`.polytropos/revision.json` in its copy) may add dependencies or name new tasks; any key that
would touch a brief, acceptance, verify command, status, or budget is refused whole. Proposals
are recorded, never applied, unless `--accept-revisions` is passed, and then only dependency
additions that keep the graph valid.

WHAT IS NOT PROVEN. No live model has been run in parallel from this repository; the `stub`
harness is the conformance executor and `cursor` is the one adapter wired. Isolation is of
FILES: two workers on one machine still share the network, the credentials the dispatch
environment carries, and whatever a verify command reaches outside its copy (the execution
boundary bounds that, as for every driver). Cancellation stops what has not started and
releases its claims; a dispatch already running is bounded by the process runner's clock and
its allowance is spent whatever it returns.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import shlex
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_VERSION = "polytropos.integration-manifest/1"
DEFAULT_MAX_PARALLEL = 1
MAX_MAX_PARALLEL = 8
#: Directories never copied into a worker's tree, and never compared: version control, the
#: graph cache, interpreter caches, dependency trees, and the proposal channel itself.
EXCLUDED_DIRS = (".git", "graphify-out", "__pycache__", ".venv", "node_modules", ".polytropos")
MAX_SNAPSHOT_FILES = 20000
MAX_HASH_BYTES = 50 * 1024 * 1024
DIAGNOSTIC_CHARS = 600
REVISION_REL = ".polytropos/revision.json"
REVISION_MAX_BYTES = 16384
REVISION_KEYS = ("reason", "add_depends", "new_tasks")
REVISION_FORBIDDEN = ("brief", "acceptance", "verify", "status", "model", "remove_depends",
                      "budget", "roles", "workflow", "routing", "capabilities")
HARNESSES = ("stub", "cursor")
WORKSPACES_DIR = "workspaces"
#: Where each harness's integrating model would read its long-context threshold, under that
#: file's own field name (HANDOFF.md, step-24 amendment). No shared schema: these never merge.
THRESHOLD_FIELDS = {
    "codex": ("data/pricing.codex.json", ("long_context", "threshold_input_tokens")),
    "copilot": ("data/pricing.copilot.json", ("long_context", "threshold_tokens")),
    "claude-code": ("data/pricing.json", ("context_window",)),
    "cursor": ("data/pricing.cursor.json", None),
}

_SIBLINGS = {}


def _sibling(name):
    if name not in _SIBLINGS:
        path = Path(__file__).resolve().with_name(f"{name}.py")
        spec = importlib.util.spec_from_file_location(f"polytropos_{name}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SIBLINGS[name] = module
    return _SIBLINGS[name]


def _kc():
    return _sibling("kit_contract")


def _sp():
    return _sibling("safe_paths")


def _pr():
    return _sibling("proc_runner")


def _ep():
    return _sibling("exec_policy")


def _cw():
    return _sibling("context_weight")


class SchedulerError(RuntimeError):
    """A run that cannot proceed: named, before anything is dispatched."""


# ---- the tree: snapshots and write sets -------------------------------------------------------------

def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _file_key(path):
    st = path.stat()
    if st.st_size > MAX_HASH_BYTES:
        return f"size:{st.st_size}:mtime:{st.st_mtime_ns}"
    return _sha(path.read_bytes())


def index_tree(root, excluded=EXCLUDED_DIRS):
    """{relative path: content key} for every regular file under `root` -> the index.

    Symlinks are not followed and not indexed (a link is not content this can copy or judge);
    excluded directories are skipped by name at any depth. Bounded by `MAX_SNAPSHOT_FILES`.
    """
    root = Path(root)
    index = {}
    count = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in excluded
                             and not Path(dirpath, d).is_symlink())
        for name in sorted(filenames):
            path = Path(dirpath, name)
            if path.is_symlink() or not path.is_file():
                continue
            count += 1
            if count > MAX_SNAPSHOT_FILES:
                raise SchedulerError(
                    f"workspace {root} holds more than {MAX_SNAPSHOT_FILES} files; refusing to "
                    f"snapshot it (exclude build output, or run sequentially)")
            index[str(path.relative_to(root).as_posix())] = _file_key(path)
    return index


def snapshot_tree(src_root, dest_root, excluded=EXCLUDED_DIRS):
    """Copy `src_root`'s files into `dest_root` through the confined writer -> the index.

    File modes are preserved (a verify script must stay executable); symlinks and excluded
    directories are left out, so the copy is a history-free tree, as repo_bench's sandboxes
    are. The index returned is of the SOURCE at copy time -- the baseline both the write set
    and the user-change check compare against.
    """
    src_root, dest_root = Path(src_root), Path(dest_root)
    sp = _sp()
    dest_root.mkdir(parents=True, exist_ok=True)
    index = index_tree(src_root, excluded)
    for rel in index:
        src = src_root / rel
        mode = src.stat().st_mode & 0o777
        sp.confined_write_bytes(dest_root, rel, src.read_bytes(), what="scheduler snapshot",
                                mode=mode or 0o644, create_parents=True)
    return index


def write_set(before, after):
    """What changed between two indexes -> {"changed": [...], "added": [...], "removed": [...]}."""
    changed = sorted(p for p in after if p in before and after[p] != before[p])
    added = sorted(p for p in after if p not in before)
    removed = sorted(p for p in before if p not in after)
    return {"changed": changed, "added": added, "removed": removed}


def write_set_paths(ws):
    return set(ws["changed"]) | set(ws["added"]) | set(ws["removed"])


def coordinator_paths(paths, kit_rel):
    """The paths in a write set that are the kit's own files (coordinator state)."""
    if kit_rel is None:
        return []
    prefix = kit_rel.rstrip("/") + "/"
    return sorted(p for p in paths if p.startswith(prefix) or p == kit_rel)


# ---- plan-revision proposals ----------------------------------------------------------------------------

def read_revision(workspace, tasks):
    """A worker's proposal, validated -> None, or {"ok": bool, "reason"/"proposal": ...}.

    Bounded in size and in shape. Only `reason`, `add_depends` ({task: [dep, ...]}), and
    `new_tasks` ([{id, title, reason}]) are accepted; any forbidden key refuses the whole
    file, because a proposal that also rewrites a verify command is not a proposal.
    """
    path = Path(workspace) / REVISION_REL
    if not path.is_file() or path.is_symlink():
        return None
    raw = path.read_bytes()
    if len(raw) > REVISION_MAX_BYTES:
        return {"ok": False, "reason": f"revision proposal exceeds {REVISION_MAX_BYTES} bytes"}
    try:
        payload = json.loads(raw.decode("utf-8", "replace"))
    except ValueError as exc:
        return {"ok": False, "reason": f"revision proposal is not JSON: {exc}"}
    if not isinstance(payload, dict):
        return {"ok": False, "reason": "revision proposal must be a JSON object"}
    forbidden = sorted(k for k in payload if k in REVISION_FORBIDDEN)
    if forbidden:
        return {"ok": False, "reason": f"revision proposal touches {', '.join(forbidden)}, which "
                                       f"a worker may not change; refused whole"}
    unknown = sorted(k for k in payload if k not in REVISION_KEYS)
    if unknown:
        return {"ok": False, "reason": f"revision proposal has unknown key(s) {', '.join(unknown)}"}
    ids = {t["id"] for t in tasks}
    add = payload.get("add_depends") or {}
    if not isinstance(add, dict) or any(
            not isinstance(v, list) or not all(isinstance(d, str) for d in v) for v in add.values()):
        return {"ok": False, "reason": "add_depends must map a task id to a list of task ids"}
    for tid, deps in add.items():
        missing = [d for d in [tid, *deps] if d not in ids]
        if missing:
            return {"ok": False, "reason": f"add_depends names unknown task(s) {', '.join(missing)}"}
    new_tasks = payload.get("new_tasks") or []
    if not isinstance(new_tasks, list) or any(
            not isinstance(n, dict) or not isinstance(n.get("id"), str)
            or not isinstance(n.get("title"), str) for n in new_tasks):
        return {"ok": False, "reason": "new_tasks must be a list of {id, title, reason} objects"}
    reason = payload.get("reason")
    if reason is not None and not isinstance(reason, str):
        return {"ok": False, "reason": "reason must be a string"}
    return {"ok": True, "proposal": {
        "reason": (reason or "")[:500],
        "add_depends": {tid: sorted(set(deps)) for tid, deps in add.items()},
        "new_tasks": [{"id": n["id"][:64], "title": n["title"][:200],
                       "reason": str(n.get("reason") or "")[:300]} for n in new_tasks][:20],
    }}


def apply_dependency_additions(tasks_text, additions):
    """TASKS.md text with `- depends:` extended -> (new_text, findings).

    The only revision this file applies on its own: an added edge can only delay a task, and
    the result is re-validated as a graph, so a proposal that would close a cycle is refused
    with the finding rather than written.
    """
    kc = _kc()
    lines = tasks_text.splitlines(keepends=True)
    current = None
    out = []
    for line in lines:
        s = line.strip()
        if s.startswith("### "):
            heading = s[4:]
            current = heading.split(kc.EM_DASH, 1)[0].strip() if kc.EM_DASH in heading \
                else heading.split(" ", 1)[0].strip()
        if current in additions and s.startswith("- depends:"):
            existing = s[len("- depends:"):].strip()
            have = [] if existing in ("", "(none)") else [d.strip() for d in existing.split(",")]
            merged = have + [d for d in additions[current] if d not in have]
            indent = line[:len(line) - len(line.lstrip())]
            line = f"{indent}- depends: {', '.join(merged)}\n"
        out.append(line)
    new_text = "".join(out)
    findings = kc.validate_graph(kc.parse_tasks(new_text))
    return new_text, findings


# ---- the integration manifest and its bound ----------------------------------------------------------------

def manifest_bound(harness, model_id, repo_root=REPO_ROOT):
    """The integrating model's long-context threshold, from ITS harness's pricing file.

    Read under that file's own field name; `None` when the model carries none (or the harness
    records none, as Cursor's file does), which the report states rather than assuming a
    figure. Never a price, never a second estimator.
    """
    if harness not in THRESHOLD_FIELDS:
        raise SchedulerError(f"no pricing file is known for integrator harness {harness!r}")
    rel, field = THRESHOLD_FIELDS[harness]
    path = Path(repo_root) / rel
    payload = json.loads(path.read_text(encoding="utf-8"))
    value = None
    if field is not None and model_id:
        node = (payload.get("models") or {}).get(model_id)
        for key in field:
            node = node.get(key) if isinstance(node, dict) else None
        value = node if isinstance(node, int) and node > 0 else None
    return {
        "harness": harness, "model": model_id, "pricing_file": rel,
        "field": ".".join(field) if field else None, "threshold_tokens": value,
        "note": (f"{rel} records no long-context threshold for {model_id!r}; the manifest is "
                 f"unbounded and this report says so" if value is None else
                 f"{rel} models[{model_id}].{'.'.join(field)} = {value} tokens"),
    }


def estimate_tokens(text):
    chars = _cw().EST_CHARS_PER_TOKEN
    return -(-len(text) // chars)


def build_manifest(batch_id, entries, harness):
    """The integration input: artifact paths, verdicts, bounded diagnostics. No transcripts."""
    return {
        "v": MANIFEST_VERSION, "batch": batch_id, "harness": harness,
        "tasks": [{
            "id": e["task"]["id"], "run": e["run"], "verdict": e["result"]["status"],
            "failure": e["result"].get("failure"), "verify_rc": e["result"].get("verify_rc"),
            "artifacts": e["write_set"], "workspace": str(e["workspace"]),
            "diagnostics": (e["result"].get("verify_evidence") or "")[-DIAGNOSTIC_CHARS:],
            "revision": e.get("revision"),
        } for e in entries],
        "sizing": None,
    }


def fit_manifest(manifest, bound):
    """Size the manifest against `bound` -> (manifest, decision) with the note recorded.

    Under the threshold: as is. Over it: diagnostics are dropped (the one field that is not
    identity) and the trim is written into the manifest; still over: refused, because the
    artifact paths alone exceed the integrating model's window and no silent truncation of
    them would be honest. No threshold: unbounded, and the sizing says so.
    """
    est = estimate_tokens(json.dumps(manifest, sort_keys=True))
    threshold = bound.get("threshold_tokens") if bound else None
    sizing = {"est_tokens": est, "threshold_tokens": threshold, "label": "est.",
              "bound": bound, "trimmed": False, "refused": False, "note": ""}
    if bound is None:
        sizing["note"] = "no integrator model named; the manifest is read mechanically here"
    elif threshold is None:
        sizing["note"] = bound["note"]
    elif est <= threshold:
        sizing["note"] = f"est. {est} tokens within {threshold}"
    else:
        for entry in manifest["tasks"]:
            entry["diagnostics"] = ""
        sizing["trimmed"] = True
        est2 = estimate_tokens(json.dumps({**manifest, "sizing": None}, sort_keys=True))
        sizing["est_tokens"] = est2
        if est2 <= threshold:
            sizing["note"] = (f"est. {est} tokens exceeded {threshold}; diagnostics dropped to "
                              f"fit (est. {est2}) -- recorded, not silent")
        else:
            sizing["refused"] = True
            sizing["note"] = (f"est. {est2} tokens exceed {threshold} even without diagnostics; "
                              f"the batch's artifact paths alone exceed the integrating model's "
                              f"window -- split the batch")
    manifest["sizing"] = sizing
    return manifest, sizing


# ---- dispatchers -------------------------------------------------------------------------------------------

class StubDispatcher:
    """A throwaway executable named by the operator: argv, never a shell string.

    `[stub, --task ID, --workspace DIR, PROMPT]`, run in the worker's copy through the process
    runner. The conformance harness for everything above; it spends nothing.
    """

    harness = "stub"

    def __init__(self, stub_bin, timeout=600):
        self.stub_bin = str(stub_bin)
        self.timeout = timeout

    def describe(self, task, prompt, workspace):
        return [self.stub_bin, "--task", task["id"], "--workspace", str(workspace), prompt]

    def __call__(self, task, prompt, workspace):
        pr = _pr()
        result = pr.run(self.describe(task, prompt, workspace), cwd=workspace,
                        timeout=self.timeout, name="stub dispatch")
        output = (result.get("stdout") or "") + (("\n" + result["stderr"]) if result.get("stderr") else "")
        return result.get("rc"), output, result


class CursorDispatcher:
    """Cursor's headless CLI in a worker's copy (`--workspace` pins it there)."""

    harness = "cursor"

    def __init__(self, cursor_bin=None, model=None, timeout=None):
        self.ca = _sibling("cursor_adapter")
        self.cursor_bin = cursor_bin or self.ca.BINARY
        self.model = model
        self.timeout = timeout or self.ca.DISPATCH_TIMEOUT_SECONDS
        self.identity = None

    def prepare(self, cwd):
        self.identity = self.ca.require_cursor(self.ca.identify(self.cursor_bin, cwd=cwd))
        return self.identity

    def describe(self, task, prompt, workspace):
        return self.ca.build_dispatch(task, model_id=self.model or task.get("model"),
                                      prompt=prompt, cursor_bin=self.cursor_bin,
                                      workspace=workspace)

    def __call__(self, task, prompt, workspace):
        pr = _pr()
        result = pr.run(self.describe(task, prompt, workspace), cwd=workspace,
                        timeout=self.timeout, name="cursor dispatch",
                        env=pr.dispatch_env("cursor"))
        output = (result.get("stdout") or "") + (("\n" + result["stderr"]) if result.get("stderr") else "")
        return result.get("rc"), output, result


def make_dispatcher(harness, stub_bin=None, cursor_bin=None, model=None):
    if harness == "stub":
        if not stub_bin:
            raise SchedulerError("--harness stub needs --stub-bin (a throwaway executable)")
        return StubDispatcher(stub_bin)
    if harness == "cursor":
        return CursorDispatcher(cursor_bin=cursor_bin, model=model)
    raise SchedulerError(f"unknown harness {harness!r}; choices: {', '.join(HARNESSES)}")


# ---- the scheduler ------------------------------------------------------------------------------------------

class Scheduler:
    """One batch of ready tasks: claim, admit, isolate, dispatch, integrate, verify, project."""

    def __init__(self, kit_dir, harness, dispatcher, *, store=None, workspace=None,
                 max_parallel=DEFAULT_MAX_PARALLEL, exec_mode="enforced", verify_factory=None,
                 keep_workspaces=False, stop_on_failure=False, accept_revisions=False,
                 integrator=None, roster_gap="stop", cancel_event=None, out=None, err=None,
                 repo_root=REPO_ROOT, workers=None):
        self.kc = _kc()
        self.kit_dir = Path(kit_dir)
        self.slug = self.kit_dir.name
        self.harness = harness
        self.actor = harness
        self.dispatcher = dispatcher
        self.store = store
        self.workspace = Path(workspace) if workspace else Path.cwd()
        self.max_parallel = max(1, min(int(max_parallel), MAX_MAX_PARALLEL))
        #: Threads actually used within a batch; defaults to the batch bound. A test pins it
        #: to one so the order of dispatch inside a batch is deterministic.
        self.workers = max(1, int(workers)) if workers else self.max_parallel
        self.exec_mode = exec_mode
        self.verify_factory = verify_factory or (
            lambda ws: _ep().verify_runner(ws, mode=self.exec_mode))
        self.keep_workspaces = keep_workspaces
        self.stop_on_failure = stop_on_failure
        self.accept_revisions = accept_revisions
        self.integrator = integrator  # (harness, model) of a model that would integrate
        self.roster_gap = roster_gap
        self.cancel = cancel_event or threading.Event()
        self.out = out or sys.stdout
        self.err = err or sys.stderr
        self.repo_root = Path(repo_root)
        self._lock = threading.Lock()
        try:
            self.kit_rel = str(self.kit_dir.resolve().relative_to(self.workspace.resolve()).as_posix())
        except ValueError:
            self.kit_rel = None

    # -- helpers --

    def say(self, line):
        print(line, file=self.out)

    def warn(self, line):
        print(line, file=self.err)

    def _ledger(self):
        return self.kc.open_ledger(self.kit_dir, store=self.store)

    def _record(self, ledger, kind, **fields):
        with self._lock:
            return ledger.append(kind, **fields)

    def _ws_root(self, batch_id):
        return Path(self._ledger().root) / WORKSPACES_DIR / batch_id

    def _batch(self, graph, ledger):
        """The tasks this run takes, in order: interrupted tasks nobody live holds (a dead
        run's work is settled first, as a driver's --task would), then the ready frontier,
        bounded by `max_parallel`."""
        al = self.kc._al()
        resumable = []
        for tid in graph["in_progress"]:
            holder = ledger.holder(tid)
            if holder is None or not al._pid_alive(holder.get("pid")):
                resumable.append(tid)
        return (resumable + [t for t in graph["frontier"] if t not in resumable])[:self.max_parallel]

    # -- planning --

    def plan(self):
        """The batch this run would take, and why -> a dict. Reads only."""
        kc = self.kc
        tasks = kc.parse_tasks(kc._read_tasks_text(self.kit_dir))
        findings = kc.validate_graph(tasks)
        freshness = kc.kit_freshness(self.kit_dir, tasks, store=self.store)
        graph = kc.graph_state(tasks, findings=findings, freshness=freshness)
        ledger = self._ledger()
        batch = self._batch(graph, ledger) if not findings else []
        plan_text = kc._plan_text(self.kit_dir)
        budget = kc.parse_plan_budget(plan_text) if plan_text else None
        notes_path = self.kit_dir / "NOTES.md"
        used = kc.combined_usage(notes_path.read_text() if notes_path.exists() else "", ledger)
        admission = kc.BudgetAdmission(budget, used) if budget else None
        admitted = []
        for tid in batch:
            ok, _reason = admission.check("initial") if admission else (True, None)
            if ok and admission:
                admission.admit("initial")
            admitted.append({"task": tid, "admitted": ok})
        held = {tid: ledger.holder(tid) for tid in batch}
        return {
            "kit": str(self.kit_dir), "harness": self.harness, "max_parallel": self.max_parallel,
            "graph": graph, "freshness": freshness, "batch": batch, "admission": admitted,
            "budget": budget, "used": used, "claims": {k: v for k, v in held.items() if v},
            "sequential": self.max_parallel == 1,
        }

    def render_plan(self, plan):
        lines = [f"scheduler plan for {plan['kit']} (harness={plan['harness']}, "
                 f"max-parallel={plan['max_parallel']}"
                 f"{' -- sequential, the default' if plan['sequential'] else ''})",
                 "  " + self.kc.render_graph_state(plan["graph"])]
        stale = [t for t, f in plan["freshness"].items() if f["state"] != "fresh"]
        for tid in sorted(stale):
            f = plan["freshness"][tid]
            lines.append(f"  evidence: {tid} {f['state']} -- {f['reason']}")
        if not plan["batch"]:
            lines.append("  batch: nothing to dispatch")
        for a in plan["admission"]:
            holder = plan["claims"].get(a["task"])
            note = "admitted" if a["admitted"] else "NOT admitted (PLAN.md budget reached)"
            if holder:
                note += f"; claimed by run {holder.get('run')} (pid {holder.get('pid')})"
            lines.append(f"  batch: {a['task']} -- {note}")
        if plan["budget"]:
            lines.append(f"  budget: {plan['budget']} used={plan['used']}")
        return "\n".join(lines)

    # -- the run --

    def run(self, dry_run=False):
        kc = self.kc
        tasks = kc.parse_tasks(kc._read_tasks_text(self.kit_dir))
        tasks_path = self.kit_dir / "TASKS.md"
        kc.exit_if_invalid_graph(tasks, tasks_path)
        plan_text = kc._plan_text(self.kit_dir)
        roster, support = kc.roster_for_run(plan_text, self.harness, self.roster_gap,
                                            slug=self.slug)
        freshness = kc.kit_freshness(self.kit_dir, tasks, store=self.store)
        graph = kc.graph_state(tasks, freshness=freshness)
        ledger = self._ledger()
        batch_ids = self._batch(graph, ledger)
        by_id = {t["id"]: t for t in tasks}
        if not batch_ids:
            reason = kc.readiness(tasks, freshness=freshness)["reason"]
            self.warn(f"{reason} ({tasks_path})")
            return {"exit": 0 if graph["state"] == "complete" else 2, "batch": [],
                    "reason": reason}
        batch_id = kc.generate_run_id()
        preamble = self._preamble()
        if dry_run:
            self.say(f"batch {batch_id}: {', '.join(batch_ids)} (max-parallel={self.max_parallel})")
            for tid in batch_ids:
                prompt = self._prompt(by_id[tid], batch_id, preamble)
                ws = self._ws_root(batch_id) / tid
                self.say(f"  {tid}: workspace {ws} (copy of {self.workspace}; not created)")
                self.say(f"  {tid}: dispatch {shlex.join(self.dispatcher.describe(by_id[tid], prompt, ws))}")
                self.say(f"  {tid}: verify {by_id[tid]['verify']}")
            self.say("dry run: nothing claimed, copied, or spawned")
            return {"exit": 0, "batch": batch_ids, "dry_run": True}

        prepare = getattr(self.dispatcher, "prepare", None)
        if prepare is not None:
            try:
                prepare(self.workspace)
            except Exception as exc:  # noqa: BLE001 -- refused before any claim
                self.warn(f"{self.harness}: {exc}")
                return {"exit": 2, "batch": [], "reason": str(exc)}

        self._record(ledger, "scheduler.batch", batch=batch_id, tasks=batch_ids,
                     max_parallel=self.max_parallel, harness=self.harness)

        # CLAIMS, then ONE admission decision for the whole batch.
        entries = []
        for tid in batch_ids:
            task = by_id[tid]
            run_id = kc.generate_run_id()
            lifecycle = kc.TaskRun(ledger, run_id, task, workspace=self.workspace,
                                   actor=self.actor, role="implementer")
            try:
                info = lifecycle.begin()
            except self.kc._al().ClaimHeld as exc:
                self.warn(f"claim: {exc}")
                continue
            kc.record_roster(lifecycle, roster, support, self.roster_gap)
            entries.append({"task": task, "run": run_id, "lifecycle": lifecycle, "info": info,
                            "result": None, "write_set": None, "workspace": None,
                            "revision": None, "index_before": None, "applied": False})
        if not entries:
            return {"exit": 2, "batch": [], "reason": "every task in the batch is claimed"}

        main_verify = self.verify_factory(self.workspace)
        budget = kc.parse_plan_budget(plan_text) if plan_text else None
        notes_path = self.kit_dir / "NOTES.md"
        used = kc.combined_usage(notes_path.read_text() if notes_path.exists() else "", ledger)
        admission = kc.BudgetAdmission(budget, used) if budget else None
        dispatching, refused = [], []
        for e in entries:
            recon = kc.reconcile_task(e["lifecycle"], e["info"], main_verify, e["task"]["verify"])
            e["recon"] = recon
            if recon["mode"] == "resolved":
                e["result"] = recon["result"]
                e["result"].update({"planned_model": e["task"].get("model"),
                                    "observed_model": None, "usd": None})
                e["write_set"] = {"changed": [], "added": [], "removed": []}
                self.warn(f"resume: task {e['task']['id']}'s check passes on the tree "
                          f"{recon['result']['reconciled']} earlier attempt(s) left; nothing "
                          f"was re-dispatched")
                continue
            kind = "retry" if recon["mode"] == "retry" else "initial"
            e["kind"] = kind
            ok, reason = admission.admit(kind) if admission else (True, None)
            if ok:
                dispatching.append(e)
            else:
                refused.append((e, reason))
        if refused:
            first, reason = refused[0]
            self.warn(f"budget-stop: {reason}; not dispatched: "
                      f"{', '.join(e['task']['id'] for e, _r in refused)}")
            key = next((k for k in budget if reason and f"{k}=" in reason), None) or "max-dispatches"
            pending = sum(1 for t in tasks if t["status"] == "pending")
            kc.append_plan_budget_stop_note(notes_path, first["task"], first["run"], key,
                                            budget.get(key), used.get(key, 0), pending,
                                            role="implementer")
            for e, r in refused:
                e["lifecycle"].end("budget-stop", reason=r)
            self._record(ledger, "scheduler.admission", batch=batch_id,
                         admitted=[e["task"]["id"] for e in dispatching],
                         refused=[e["task"]["id"] for e, _r in refused])
            entries = [e for e in entries if e not in [r for r, _ in refused]]

        # ISOLATE, then dispatch within the bound. Each worker takes its own copy and marks
        # its task in-progress only once it actually starts, so a cancelled task copied
        # nothing and its status never moved.
        ws_root = self._ws_root(batch_id)
        for e in dispatching:
            e["workspace"] = ws_root / e["task"]["id"]
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = [pool.submit(self._work, e, batch_id, preamble) for e in dispatching]
            for f in futures:
                f.result()

        # INTEGRATE from the manifest, then verify the merged tree.
        entries_alive = [e for e in entries if e["result"] is not None]
        manifest = build_manifest(batch_id, entries_alive, self.harness)
        bound = manifest_bound(self.integrator[0], self.integrator[1], self.repo_root) \
            if self.integrator else None
        manifest, sizing = fit_manifest(manifest, bound)
        manifest_rel = f"{WORKSPACES_DIR}/{batch_id}/manifest.json"
        _sp().confined_write_bytes(Path(ledger.root), manifest_rel,
                                   (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
                                   what="integration manifest", create_parents=True)
        self._record(ledger, "integration.manifest", batch=batch_id, path=manifest_rel,
                     est_tokens=sizing["est_tokens"], threshold=sizing["threshold_tokens"],
                     trimmed=sizing["trimmed"], refused=sizing["refused"], note=sizing["note"])
        if sizing["refused"]:
            self.warn(f"integration refused: {sizing['note']}")
            for e in entries_alive:
                if e["result"]["status"] == "done" and e["workspace"] is not None:
                    e["result"].update(status="blocked", failure="integration-refused")
        else:
            self._integrate(manifest, entries_alive, ledger, batch_id, main_verify)

        # PROJECT every task and record its note; release claims.
        for e in entries_alive:
            self._project(e, tasks_path, notes_path, ledger, batch_id)
        self._revisions(entries_alive, tasks, tasks_path, ledger, batch_id)
        for e in entries_alive:
            e["lifecycle"].end("cancelled" if e["result"].get("failure") == "cancelled"
                               else "finished")
        for e in dispatching:
            if (not self.keep_workspaces and e.get("applied") and e["workspace"] is not None
                    and e["result"]["status"] == "done"):
                self._discard(e["workspace"])
        exit_code = 1 if any(e["result"]["status"] in ("blocked", "cancelled")
                             for e in entries_alive) else 0
        summary = {
            "exit": exit_code, "batch": [e["task"]["id"] for e in entries_alive],
            "results": {e["task"]["id"]: e["result"]["status"] for e in entries_alive},
            "manifest": str(Path(ledger.root) / manifest_rel), "sizing": sizing,
            "cancelled": [e["task"]["id"] for e in entries_alive
                          if e["result"].get("failure") == "cancelled"],
        }
        self.say(f"batch {batch_id}: " + ", ".join(
            f"{tid}={st}" for tid, st in summary["results"].items())
            + f" (manifest {manifest_rel}, {sizing['label']} {sizing['est_tokens']} tokens)")
        return summary

    # -- one worker --

    def _preamble(self):
        if self.harness == "cursor":
            path = self.repo_root / "cursor" / "agents" / "polytropos-implementer.md"
            if path.exists():
                text = path.read_text(encoding="utf-8")
                parts = text.split("---", 2)
                return (parts[2] if len(parts) == 3 and text.startswith("---") else text).strip()
        return ("You implement ONE task of a polytropos execution kit in an isolated copy of the "
                "workspace. Do exactly what the brief says; never edit the kit's own files; run "
                "the task's verify command before you report. Your copy is integrated by the "
                "coordinator only if nothing conflicts.")

    def _prompt(self, task, batch_id, preamble):
        head = self.kc.build_id_preamble(kit=self.slug, run_id=batch_id, task_id=task["id"])
        body = preamble + "\n\n---\n\n" + task["brief"]
        return f"{head}\n\n{body}" if head else body

    def _work(self, e, batch_id, preamble):
        kc = self.kc
        task, lifecycle, ws = e["task"], e["lifecycle"], e["workspace"]
        base = {"id": task["id"], "model_used": getattr(self.dispatcher, "model", None) or task.get("model"),
                "planned_model": task.get("model"), "observed_model": None, "escalations": [],
                "dispatch_rc": None, "usd": None, "role": "implementer"}
        if self.cancel.is_set():
            self._record(lifecycle.ledger, "scheduler.cancelled", batch=batch_id, run=e["run"],
                         task=task["id"], reason="cancelled before dispatch; nothing spent")
            e["result"] = {**base, "status": "cancelled", "verify_rc": None,
                           "failure": "cancelled", "class": None}
            e["write_set"] = {"changed": [], "added": [], "removed": []}
            e["workspace"] = None
            return
        with self._lock:
            kc.project_status(self.kit_dir / "TASKS.md", task["id"], "in-progress")
        e["index_before"] = snapshot_tree(self.workspace, ws)
        prompt = self._prompt(task, batch_id, preamble)
        if e.get("recon", {}).get("mode") == "retry":
            prompt += e["recon"]["context"]
        with self._lock:
            attempt = lifecycle.attempt_started(e["kind"], base["model_used"], prompt,
                                                task["verify"])
        try:
            raw = self.dispatcher(task, prompt, ws)
        except Exception as exc:  # noqa: BLE001 -- a dispatcher that raised is a failed start
            raw = (126, f"dispatch failed to start: {exc}", {"outcome": "start-failed"})
        rc, output, proc = (raw + ({},))[:3] if isinstance(raw, tuple) else (None, "", {})
        proc = proc if isinstance(proc, dict) else {}
        with self._lock:
            cls = lifecycle.attempt_finished(attempt, rc, output or "",
                                             proc_outcome=proc.get("outcome"))
        after = index_tree(ws)
        e["write_set"] = write_set(e["index_before"], after)
        e["revision"] = read_revision(ws, self._tasks_for_revision())
        touched = coordinator_paths(write_set_paths(e["write_set"]), self.kit_rel)
        if touched:
            self._record(lifecycle.ledger, "security.violation", batch=batch_id, run=e["run"],
                         task=task["id"], violation="coordinator-state-edit", paths=touched)
            e["result"] = {**base, "status": "blocked", "verify_rc": None, "dispatch_rc": rc,
                           "failure": "coordinator-state-edit", "class": None,
                           "verify_evidence": f"worker edited coordinator state: {', '.join(touched)}"}
        elif rc is not None and rc != 0:
            e["result"] = {**base, "status": "blocked", "verify_rc": None, "dispatch_rc": rc,
                           "failure": "dispatch", "class": cls,
                           "verify_evidence": " ".join((output or "").split())[-2000:]}
        else:
            try:
                vrc, vout = self.verify_factory(ws)(task["verify"])
            except OSError as exc:
                vrc, vout = 126, f"verify failed to start: {exc}"
            with self._lock:
                lifecycle.verify_finished(attempt, vrc, vout)
            e["result"] = {**base, "status": "done" if vrc == 0 else "blocked", "verify_rc": vrc,
                           "dispatch_rc": rc, "failure": None if vrc == 0 else "verification",
                           "class": None, "verify_evidence": " ".join((vout or "").split())[-2000:]}
        if e["result"]["status"] == "blocked" and self.stop_on_failure:
            self.cancel.set()

    def _tasks_for_revision(self):
        return self.kc.parse_tasks(self.kc._read_tasks_text(self.kit_dir))

    # -- integration --

    def _integrate(self, manifest, entries, ledger, batch_id, main_verify):
        """Apply each accepted write set from the MANIFEST, then verify the merged tree."""
        sp = _sp()
        by_id = {e["task"]["id"]: e for e in entries}
        applied_paths = set()
        current = index_tree(self.workspace)
        for m in manifest["tasks"]:
            e = by_id[m["id"]]
            if m["verdict"] != "done" or e["workspace"] is None:
                continue
            ws = e["workspace"]
            paths = write_set_paths(m["artifacts"])
            if not paths:
                e["applied"] = True
                continue
            overlap = sorted(paths & applied_paths)
            user_changed = sorted(
                p for p in paths
                if (p in current and p in e["index_before"] and current[p] != e["index_before"][p])
                or (p in current and p not in e["index_before"]))
            if overlap or user_changed:
                why = []
                if overlap:
                    why.append(f"also written by another task in this batch: {', '.join(overlap)}")
                if user_changed:
                    why.append(f"changed in the workspace while the batch ran: {', '.join(user_changed)}")
                self._record(ledger, "integration.conflict", batch=batch_id, run=e["run"],
                             task=m["id"], overlap=overlap, user_changed=user_changed,
                             workspace=str(ws))
                e["result"].update(status="blocked", failure="integration-conflict",
                                   verify_evidence=f"integration conflict -- {'; '.join(why)}; the "
                                                   f"worker's tree is kept at {ws}; nothing was applied "
                                                   f"and nothing was reset")
                continue
            for rel in list(m["artifacts"]["changed"]) + list(m["artifacts"]["added"]):
                src = Path(ws) / rel
                mode = src.stat().st_mode & 0o777
                sp.confined_write_bytes(self.workspace, rel, src.read_bytes(),
                                        what="scheduler integrate", mode=mode or 0o644,
                                        create_parents=True)
                current[rel] = _file_key(src)
            for rel in m["artifacts"]["removed"]:
                sp.confined_unlink(self.workspace, rel, what="scheduler integrate", missing_ok=True)
                current.pop(rel, None)
            applied_paths |= paths
            e["applied"] = True
            self._record(ledger, "integration.applied", batch=batch_id, run=e["run"], task=m["id"],
                         changed=len(m["artifacts"]["changed"]), added=len(m["artifacts"]["added"]),
                         removed=len(m["artifacts"]["removed"]))
        # FRESH VERIFICATION on the merged tree, for every task that was applied.
        for e in entries:
            if not e.get("applied") or e["result"]["status"] != "done" or e["workspace"] is None:
                continue
            try:
                vrc, vout = main_verify(e["task"]["verify"])
            except OSError as exc:
                vrc, vout = 126, f"verify failed to start: {exc}"
            self._record(ledger, "integration.verified", batch=batch_id, run=e["run"],
                         task=e["task"]["id"], rc=vrc)
            e["result"]["merged_verify_rc"] = vrc
            if vrc != 0:
                e["result"].update(status="blocked", failure="merged-tree-verification",
                                   verify_rc=vrc,
                                   verify_evidence=("passed in its own copy, fails on the merged "
                                                    "tree; the applied files were NOT reset: "
                                                    + " ".join((vout or "").split())[-1500:]))

    def _project(self, e, tasks_path, notes_path, ledger, batch_id):
        kc = self.kc
        task, result, lifecycle = e["task"], e["result"], e["lifecycle"]
        ws = e["write_set"] or {"changed": [], "added": [], "removed": []}
        if result.get("failure") == "cancelled":
            # Not a verdict: nothing ran, the status never moved, and the line says so with
            # zero attempts -- the budget-stop rule applied to cancellation.
            kc.append_block(notes_path, "\n".join([
                f"## {kc.datetime.now(kc.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"
                f"{kc.EM_DASH}{task['id']}",
                "- role: implementer", f"- harness: {self.actor}",
                f"- scheduler: batch {batch_id} cancelled this task before dispatch; nothing "
                f"spent, status unchanged",
                "- " + kc.build_outcome_line(task["id"], "unpinned", 0, "cancelled",
                                             run_id=e["run"]),
            ]) + "\n")
            return
        kc.finish_task_projection(lifecycle, tasks_path, task, result)
        extra = [f"- scheduler: batch {batch_id}, max-parallel {self.max_parallel}, isolated copy "
                 f"{'kept' if (e['workspace'] and (self.keep_workspaces or result['status'] == 'blocked')) else 'discarded'}",
                 f"- write-set: {len(ws['changed'])} changed, {len(ws['added'])} added, "
                 f"{len(ws['removed'])} removed"]
        if result.get("merged_verify_rc") is not None:
            extra.append(f"- merged-tree verify: exit {result['merged_verify_rc']}")
        if result.get("failure") in ("integration-conflict", "coordinator-state-edit",
                                     "merged-tree-verification", "integration-refused", "cancelled"):
            extra.append(f"- {result['failure']}: {result.get('verify_evidence', '')[:600]}")
        if e.get("revision"):
            rev = e["revision"]
            extra.append("- plan-revision: " + (
                f"proposed ({rev['proposal']['reason'][:120] or 'no reason given'})" if rev["ok"]
                else f"refused ({rev['reason']})"))
        kc.append_run_note(notes_path, result, task, run_id=e["run"], actor=self.actor,
                           extra=extra)
        lifecycle.project(result["status"], kc.outcome_result(result["status"],
                                                              result.get("escalations") or [], None),
                          outcome_line=True)

    def _revisions(self, entries, tasks, tasks_path, ledger, batch_id):
        """Record every proposal; apply only accepted dependency additions, revalidated."""
        kc = self.kc
        additions = {}
        for e in entries:
            rev = e.get("revision")
            if not rev:
                continue
            if not rev["ok"]:
                self._record(ledger, "plan.revision-refused", batch=batch_id, run=e["run"],
                             task=e["task"]["id"], reason=rev["reason"])
                self.warn(f"plan-revision: task {e['task']['id']}'s proposal refused -- {rev['reason']}")
                continue
            p = rev["proposal"]
            affected = sorted({tid for tid in p["add_depends"]} | {d for ds in p["add_depends"].values() for d in ds})
            self._record(ledger, "plan.revision-proposed", batch=batch_id, run=e["run"],
                         task=e["task"]["id"], add_depends=p["add_depends"],
                         new_tasks=[n["id"] for n in p["new_tasks"]], affected=affected,
                         reason=p["reason"])
            self.warn(f"plan-revision: task {e['task']['id']} proposes add_depends="
                      f"{p['add_depends']} new_tasks={[n['id'] for n in p['new_tasks']]} "
                      f"(affected: {', '.join(affected) or 'none'}); "
                      + ("applying dependency additions" if self.accept_revisions and p["add_depends"]
                         else "recorded, not applied"
                         + ("" if not p["new_tasks"] else "; new tasks are the architect's to add")))
            if self.accept_revisions:
                for tid, deps in p["add_depends"].items():
                    additions.setdefault(tid, [])
                    additions[tid] += [d for d in deps if d not in additions[tid]]
        if additions:
            text = tasks_path.read_text()
            new_text, findings = apply_dependency_additions(text, additions)
            if findings:
                self._record(ledger, "plan.revision-refused", batch=batch_id,
                             reason="dependency additions would invalidate the graph",
                             findings=[f.get("kind", str(f)) if isinstance(f, dict) else str(f) for f in findings])
                self.warn("plan-revision: dependency additions refused -- "
                          + kc.render_findings(findings).replace("\n", " "))
                return
            tmp = tasks_path.with_suffix(".md.tmp")
            tmp.write_text(new_text)
            os.replace(tmp, tasks_path)
            self._record(ledger, "plan.revised", batch=batch_id, add_depends=additions)
            self.warn(f"plan-revision: applied add_depends={additions}; the graph revalidated")

    def _discard(self, ws):
        import shutil
        try:
            shutil.rmtree(ws)
        except OSError:
            pass


# ---- demo -------------------------------------------------------------------------------------------------------

DEMO_STUB = """#!/bin/sh
# argv: --task ID --workspace DIR PROMPT ; writes out-<ID>.txt in the workspace copy
task="$2"
printf 'made by %s\\n' "$task" > "out-$task.txt"
%EXTRA%
exit 0
"""


def _demo(out=None):
    out = out or sys.stdout

    def say(line=""):
        print(line, file=out)

    kc = _kc()
    with tempfile.TemporaryDirectory(prefix="kit_scheduler_demo_") as tmp:
        root = Path(tmp)
        kit = root / ".claude" / "kits" / "demo"
        kit.mkdir(parents=True)
        (kit / "TASKS.md").write_text(
            "## Phase 1 — demo\n\n"
            "### T1 — first\n- status: pending\n- depends: (none)\n- independent: yes\n\n"
            "**Brief.** write out-T1.txt\n\n**Acceptance.** file exists\n\n**Verify.**\n```bash\ntest -f out-T1.txt\n```\n\n"
            "### T2 — second\n- status: pending\n- depends: (none)\n- independent: yes\n\n"
            "**Brief.** write out-T2.txt\n\n**Acceptance.** file exists\n\n**Verify.**\n```bash\ntest -f out-T2.txt\n```\n\n"
            "### T3 — joins\n- status: pending\n- depends: T1, T2\n\n"
            "**Brief.** needs both\n\n**Acceptance.** both exist\n\n**Verify.**\n```bash\ntest -f out-T1.txt && test -f out-T2.txt\n```\n")
        (kit / "PLAN.md").write_text("# demo\n\nbudget: max-dispatches=3\n")
        stub = root / "demo-stub"
        stub.write_text(DEMO_STUB.replace("%EXTRA%", ""))
        stub.chmod(0o755)
        store = root / "store"
        say("== two independent tasks, one batch of two, integrated and verified on the merged tree ==")
        sched = Scheduler(kit, "stub", StubDispatcher(stub), store=store, workspace=root,
                          max_parallel=2, exec_mode="trusted-host", out=out, err=out)
        say("  " + sched.render_plan(sched.plan()).replace("\n", "\n  "))
        summary = sched.run()
        say(f"  results: {summary['results']}; merged tree has: "
            f"{sorted(p.name for p in root.glob('out-*.txt'))}")
        say()
        say("== the third task is ready only now; the budget has one dispatch left ==")
        say("  " + sched.render_plan(sched.plan()).replace("\n", "\n  "))
        say()
        say("== a conflicting pair: both workers write the same file ==")
        (kit / "TASKS.md").write_text((kit / "TASKS.md").read_text().replace(
            "- status: done", "- status: pending").replace("- depends: T1, T2", "- depends: (none)"))
        (kit / "PLAN.md").write_text("# demo\n\nbudget: max-dispatches=9\n")
        stub.write_text(DEMO_STUB.replace("%EXTRA%", "printf 'from %s\\n' \"$task\" > shared.txt"))
        for p in root.glob("out-*.txt"):
            p.unlink()
        summary = sched.run()
        say(f"  results: {summary['results']}")
        say(f"  shared.txt in the merged tree: {(root / 'shared.txt').read_text().strip()!r}")
        say()
        say("== integration manifest, sized against an integrating model's window ==")
        say(f"  {summary['sizing']['label']} {summary['sizing']['est_tokens']} tokens -- {summary['sizing']['note']}")
        bound = manifest_bound("cursor", "any")
        say(f"  cursor bound: {bound['note']}")


# ---- CLI --------------------------------------------------------------------------------------------------------

def build_parser():
    ap = argparse.ArgumentParser(
        prog="kit_scheduler.py",
        description="Artifact-aware scheduling for execution kits. Sequential by default; "
                    "--max-parallel above one runs ready independent tasks in isolated copies of "
                    "the workspace, integrates their write sets, and verifies the merged tree. A "
                    "real run with --harness cursor spends the user's allowance; --dry-run and "
                    "demo spawn nothing.")
    sub = ap.add_subparsers(dest="command", required=True)
    p_plan = sub.add_parser("plan", help="the batch this run would take, and why (reads only)")
    p_plan.add_argument("--kit", required=True)
    p_plan.add_argument("--max-parallel", type=int, default=DEFAULT_MAX_PARALLEL)
    p_plan.add_argument("--attempt-store", default=None)
    p_plan.add_argument("--workspace", default=None)
    p_plan.add_argument("--json", action="store_true")
    p_run = sub.add_parser("run", help="claim, admit, isolate, dispatch, integrate, verify")
    p_run.add_argument("--kit", required=True)
    p_run.add_argument("--harness", choices=HARNESSES, required=True)
    p_run.add_argument("--max-parallel", type=int, default=DEFAULT_MAX_PARALLEL,
                       help=f"1 (default) is sequential; at most {MAX_MAX_PARALLEL}")
    p_run.add_argument("--stub-bin", default=None, help="the stub executable (--harness stub)")
    p_run.add_argument("--cursor-bin", default=None)
    p_run.add_argument("--model", default=None, help="passed to the harness as written")
    p_run.add_argument("--attempt-store", default=None)
    p_run.add_argument("--workspace", default=None, help="the main workspace (default: cwd)")
    p_run.add_argument("--exec-mode", choices=("enforced", "trusted-host"), default="enforced")
    p_run.add_argument("--keep-workspaces", action="store_true")
    p_run.add_argument("--stop-on-failure", action="store_true",
                       help="cancel tasks not yet started when one fails")
    p_run.add_argument("--accept-revisions", action="store_true",
                       help="apply proposed dependency additions that keep the graph valid")
    p_run.add_argument("--integrator-harness", choices=tuple(THRESHOLD_FIELDS), default=None,
                       help="size the manifest for this harness's integrating model")
    p_run.add_argument("--integrator-model", default=None)
    p_run.add_argument("--roster-gap", choices=_kc().GAP_MODES, default="stop")
    p_run.add_argument("--dry-run", action="store_true")
    sub.add_parser("demo", help="two independent tasks integrated, a conflict, a sized manifest")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "demo":
        _demo()
        return 0
    if args.command == "plan":
        sched = Scheduler(args.kit, "stub", None, store=args.attempt_store,
                          workspace=args.workspace, max_parallel=args.max_parallel)
        plan = sched.plan()
        if args.json:
            print(json.dumps(plan, indent=2, sort_keys=True, default=str))
        else:
            print(sched.render_plan(plan))
        return 0
    try:
        dispatcher = make_dispatcher(args.harness, stub_bin=args.stub_bin,
                                     cursor_bin=args.cursor_bin, model=args.model)
        integrator = None
        if args.integrator_harness:
            integrator = (args.integrator_harness, args.integrator_model)
        sched = Scheduler(args.kit, args.harness, dispatcher, store=args.attempt_store,
                          workspace=args.workspace, max_parallel=args.max_parallel,
                          exec_mode=args.exec_mode, keep_workspaces=args.keep_workspaces,
                          stop_on_failure=args.stop_on_failure,
                          accept_revisions=args.accept_revisions, integrator=integrator,
                          roster_gap=args.roster_gap)
        try:
            summary = sched.run(dry_run=args.dry_run)
        except KeyboardInterrupt:
            sched.cancel.set()
            print("cancelled: tasks not yet started are released; a running dispatch is bounded "
                  "by the process runner and its allowance is spent", file=sys.stderr)
            return 130
    except SchedulerError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return summary.get("exit", 0)


if __name__ == "__main__":
    sys.exit(main())
