#!/usr/bin/env python3
"""The attempt ledger: what a run did, written before and after it did it, outside the tree
it did it to.

WHAT WAS WRONG. Three kinds of state existed and none of them was a record of an attempt.
`TASKS.md` carries a task's status, which a crash leaves at `in-progress` with no way to tell
a run that died before dispatch from one that died after the model had already been paid.
`NOTES.md` carries one `outcome:` line per FINISHED task, so an interrupted ladder -- three
escalations and a kill -- leaves nothing behind, and the next run starts its budget from zero.
Ralph wrote a state file every tick and never read it back, and its next prompt said
`last_verify_rc=1` and nothing else about what had failed.

WHAT THIS IS. An append-only JSONL event stream per kit (or per Ralph goal), one line per
fact, written through `bin/safe_paths.py` into the per-user data root (`bin/runtime_data.py`)
rather than into the workspace. An attempt is recorded BEFORE its dispatch
(`attempt.started`) and again after (`attempt.finished`); a crash in between leaves a started
attempt with no finish, which a resuming run finds and closes as `unknown` -- never as
success, and never re-dispatched as if it had not happened.

WHAT IT IS NOT. Not exactly-once execution: a process killed after the call was made has
still made the call, and nothing here can know whether the provider billed it. Not
tamper-proof: the file lives outside the workspace, so a verify command confined by
`bin/exec_policy.py` cannot reach it, but a dispatch is not confined (SECURITY.md), and a
worker running with the user's own privileges can write anywhere the user can. What the
location buys is that the ordinary paths -- a verify command, a git operation in the
workspace, a synced or committed tree -- do not touch it.

ONE SOURCE OF TRUTH. `TASKS.md` status and the `NOTES.md` outcome line are PROJECTIONS of
this ledger, written after it and recorded here as `task.projected` once they have been. A
resume that finds a finished attempt with no projection re-projects; it does not re-run.

PROVENANCE, AND WHY IT IS A POINTER. An attempt used to record WHAT ran and nothing about the
decisions it ran under: which acceptance criteria it was judged against, which policy bundle
the run was pinned to, which decision record chose the model, which budget grant admitted the
call. `PROVENANCE_REFS` adds those four as OPTIONAL references -- an id, the digest of the
bytes the referenced object had, and that object's own contract version. The object itself
stays in the store that owns it; the ledger carries the pointer, because a line here is
bounded (`MAX_LINE_BYTES`) and a rubric or a state snapshot is not a line. Absent is UNKNOWN,
read-time, with no back-fill: an attempt recorded before these existed has none, and that is
recorded as exactly that rather than rounded to a default.

CLASSIFYING FAILURE. An attempt that fails because the CLI is missing, the account is logged
out, a flag is unknown, or the network is down fails the same way on a more expensive model.
`classify_dispatch` names those classes so `recovery_for` can say "stop" rather than "escalate",
and so an infrastructure failure is never written into the routing history as a verdict on
the model that never got to run.

PROGRESS IS NOT "THE LOG CHANGED". Ralph halted when the last N verify outputs hashed
identical, so a timestamp in the test runner's summary line defeated the detector and a
genuine fix with a similar log tripped it. `signature` hashes a NORMALIZED output;
`failure_count` reads the runner's own failure tally where it prints one; `progress` decides
from exit code, failure count, signature and whether the tree changed at all, in that order.
"""

import hashlib
import importlib.util
import json
import os
import re
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

#: Version stamped on every event line. A reader checks it before trusting field names.
LEDGER_VERSION = "polytropos.attempts/1"

#: The `runtime_data` store this ledger lives in.
STORE = "attempts"

EVENTS_FILE = "events.jsonl"
CLAIMS_DIR = "claims"

#: Longest event line accepted. Text fields are bounded well below this before serialization;
#: exceeding it means a caller bypassed the bounding, and that is refused rather than written.
MAX_LINE_BYTES = 16 * 1024

#: How much of a verify output's tail and of a dispatch's own report is retained. Both are
#: redacted before retention (`bin/redact.py`) because they travel into the next prompt.
TAIL_CHARS = 2000
REPORT_CHARS = 800

#: Wall clock for the local `git` reads that fingerprint a workspace. Short on purpose: a
#: fingerprint is optional evidence, and a hung `git` must not stall the attempt it describes.
GIT_PROBE_TIMEOUT_SECONDS = 20

#: What kind of consuming operation an attempt is. The first six mirror `kit_contract`'s
#: `OPERATION_CAPS`; `tick` is Ralph's, which has no kit and no ladder.
OPERATIONS = ("initial", "retry", "escalation", "consult", "review", "acceptance", "tick")

#: Why an attempt failed. `model` and `verification` are the model's problem; the rest are the
#: environment's, and retrying them on a costlier model buys nothing. `unknown` is a non-zero
#: exit nothing here could attribute, and it is treated like the environment's: stop and show
#: the operator, because the old behaviour on an unexplained failed dispatch was to stop too.
CLASSES = ("model", "verification", "infrastructure", "auth", "config", "permission", "unknown")

RECOVERY = {
    "model": "escalate",
    "verification": "escalate",
    "infrastructure": "stop",
    "auth": "stop",
    "config": "stop",
    "permission": "stop",
    "unknown": "stop",
}

#: The outcome a resuming run assigns to an attempt whose process left no result behind.
OUTCOME_UNKNOWN = "unknown"

#: PROVENANCE: which decisions an attempt was made under. Each name points at an object that
#: lives in its OWN store under its OWN contract version -- the acceptance criteria the attempt
#: was dispatched against, the policy bundle the run is pinned to, the decision record that
#: produced the selection, and the budget grant that admitted the operation. All four are
#: optional on every event that accepts them.
#:
#: WHY THEY ARE OPTIONAL AND WHY `LEDGER_VERSION` DID NOT MOVE FOR THEM. `events()` skips and
#: counts as CORRUPT every line whose `v` is not `LEDGER_VERSION`. Bumping the constant for an
#: additive field would therefore make every historical event in every user's store unreadable,
#: and silently -- they would surface as a corruption count, not as a migration. So these fields
#: are additive and absent-means-unknown, the line keeps `polytropos.attempts/1`, and the
#: migration is READ-TIME ONLY: nothing is back-filled, reconstructed or back-dated. An attempt
#: recorded before these references existed has none and never acquires one. A genuinely
#: incompatible shape belongs on the REFERENCED object's own contract version (and in
#: `release_gate.VERSION_SOURCES`), never on the ledger line that points at it.
PROVENANCE_REFS = ("acceptance_ref", "policy_ref", "decision_ref", "admission_ref")

#: A reference is an IDENTITY, never a payload: `id` names the object, `sha` names the exact
#: bytes it had, and `v` is the REFERENCED contract's own version string -- never this ledger's,
#: which versions the event line rather than what the line points at. `sha` and `v` may be
#: genuinely unknown to the caller that records the pointer; absent is recorded as absent.
REF_FIELDS = ("id", "sha", "v")

#: Ceiling on each part of a reference. Generous for a digest or a version string, far too small
#: for a rubric, a prompt, a diff or a state snapshot -- which is the point: the ledger carries
#: the pointer and the owning store carries the object.
REF_PART_CHARS = 200


class LedgerError(RuntimeError):
    """The ledger could not record or read what it was asked to."""


class RefError(LedgerError):
    """Something offered as a provenance reference was not an identity."""


class ClaimHeld(LedgerError):
    """Another live run holds this task."""


class StaleState(LedgerError):
    """A projection was about to be written from a snapshot the file no longer matches."""


# ---- sibling loaders (bin/ is not a package) -------------------------------------------------

def _sibling(name):
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sp():
    return _sibling("safe_paths")


def _rd():
    return _sibling("redact")


def _pr():
    return _sibling("proc_runner")


def _rt():
    return _sibling("runtime_data")


# ---- identity and location --------------------------------------------------------------------

def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def new_attempt_id():
    """Content-free, like run ids: never a pid, path, hostname or timestamp."""
    return secrets.token_hex(4)


# ---- provenance references ---------------------------------------------------------------------

def make_ref(ref_id, sha=None, version=None):
    """One provenance reference -> `{"id", "sha", "v"}`.

    `ref_id` is what the object is called in the store that owns it. `sha` is the digest of the
    exact bytes that object had when this pointer was taken -- a digest IDENTIFIES content and
    is not a protection against anything. `version` is the referenced contract's own version,
    so a reader knows which field names apply to whatever it goes and fetches.

    `sha` and `version` are optional because a caller may honestly not know them; the reference
    then carries `None` there, and `ref_gaps` names what is missing rather than a reader
    assuming a default. What is refused is a non-identity: an empty or non-string id, a
    non-string part, or a part long enough to be a payload rather than a pointer.
    """
    parts = {"id": ref_id, "sha": sha, "v": version}
    if not isinstance(ref_id, str) or not ref_id.strip():
        raise RefError(
            f"a provenance reference needs a non-empty string id, got {ref_id!r}"
        )
    for name, value in parts.items():
        if value is None:
            continue
        if not isinstance(value, str):
            raise RefError(
                f"a provenance reference's {name!r} must be a string, got {type(value).__name__}"
            )
        if len(value) > REF_PART_CHARS:
            raise RefError(
                f"a provenance reference's {name!r} is {len(value)} chars; the ledger holds a "
                f"pointer, not a payload (limit {REF_PART_CHARS}) -- the object belongs in the "
                f"store that owns it"
            )
    return {"id": ref_id, "sha": sha, "v": version}


def read_ref(value):
    """A stored reference as this ledger understands it, or None when there is none.

    None is UNKNOWN, and so is anything that is not a reference. A line whose `decision_ref` is
    a number, a bare string or a dict with no id was not written by `make_ref`; guessing what it
    meant would INVENT provenance, so it reads exactly like absence. `sha` and `v` are carried
    when present and left None when not.
    """
    if not isinstance(value, dict):
        return None
    ref_id = value.get("id")
    if not isinstance(ref_id, str) or not ref_id.strip():
        return None
    out = {"id": ref_id, "sha": None, "v": None}
    for name in ("sha", "v"):
        part = value.get(name)
        if isinstance(part, str) and part:
            out[name] = part
    return out


def provenance(event):
    """What one event says about the decisions behind it -> `{name: ref or None}`.

    Every name in `PROVENANCE_REFS` is answered, so a caller never has to ask whether the key
    exists. `None` means unknown -- never a default, never a zero, and never back-filled. An
    event written before these references existed answers `None` to all four, which is the
    honest answer and the same one a caller that recorded nothing gets.
    """
    ev = event if isinstance(event, dict) else {}
    return {name: read_ref(ev.get(name)) for name in PROVENANCE_REFS}


def ref_gaps(ref):
    """Which parts of a reference are unknown -> a sorted list of `REF_FIELDS` names.

    A reference with an id but no digest and no version still points somewhere; it simply
    cannot say WHICH bytes or under WHICH contract. Naming the gap is the disclosure -- a
    partially known pointer is neither discarded nor presented as complete.
    """
    if ref is None:
        return sorted(REF_FIELDS)
    return sorted(name for name in REF_FIELDS if not ref.get(name))


def validated_refs(**refs):
    """The non-None provenance references among `refs`, each checked -> a dict to splat.

    A reference that is None is left OUT rather than written as an explicit null, so an event
    recorded without one is byte-identical to the events written before these fields existed.
    Nothing then has to tell "written without a reference" from "written before there were
    any": both are unknown, which is the same answer to the same question.
    """
    out = {}
    for name, value in refs.items():
        if name not in PROVENANCE_REFS:
            raise RefError(
                f"{name!r} is not a provenance reference; valid: {', '.join(PROVENANCE_REFS)}"
            )
        if value is None:
            continue
        ref = read_ref(value)
        if ref is None:
            raise RefError(
                f"{name} must be a reference from make_ref -- an id, optionally the content "
                f"digest and the referenced contract's version -- got {value!r}"
            )
        out[name] = ref
    return out


def kit_repo_root(kit_dir):
    """The checkout a kit belongs to: the directory holding `.claude/kits/<slug>`.

    A kit elsewhere (a fixture in a temp dir) belongs to its own parent. The answer decides
    which per-project store the ledger lives in, so two checkouts of one repo never share one.
    """
    kit_dir = Path(kit_dir).resolve()
    parent = kit_dir.parent
    if parent.name == "kits" and parent.parent.name == ".claude":
        return parent.parent.parent
    return parent


def default_store(repo_root, env=None):
    """Where the ledger lives unless a `--attempt-store` flag says otherwise."""
    return _rt().store_path(STORE, repo_root, env=env)


def namespace_for_goal(goal, verify_cmd):
    """Ralph has no kit; the same goal with the same check resumes the same ledger."""
    digest = hashlib.sha256(f"{goal or ''}\0{verify_cmd or ''}".encode("utf-8")).hexdigest()
    return f"ralph-{digest[:12]}"


def _pid_alive(pid):
    """Whether `pid` names a running process. EPERM means it exists and is not ours.

    A pid can be recycled, so a stale lock whose pid has been reused by an unrelated process
    reads as held. That is the conservative failure: a run refuses rather than running twice,
    and the operator clears it deliberately (`break_claim`).
    """
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


# ---- the ledger ------------------------------------------------------------------------------

class AttemptLedger:
    """One kit's (or one goal's) append-only event stream plus its task claims."""

    def __init__(self, root, namespace):
        sp = _sp()
        self.root = Path(root)
        self.namespace = sp.validate_id(namespace, "ledger namespace")
        self.corrupt = 0
        self._events_rel = f"{self.namespace}/{EVENTS_FILE}"

    # -- raw stream --

    @property
    def events_path(self):
        return self.root / self._events_rel

    def append(self, kind, **fields):
        """Append one event -> the event dict as written."""
        event = {"v": LEDGER_VERSION, "ts": utc_now(), "kind": kind}
        event.update(fields)
        line = json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n"
        data = line.encode("utf-8")
        if len(data) > MAX_LINE_BYTES:
            raise LedgerError(
                f"attempt ledger: refusing a {len(data)}-byte {kind} event; text fields must be "
                f"bounded before they reach the ledger"
            )
        sp = _sp()
        _rt().ensure_private(self.root)
        sp.confined_append_bytes(self.root, self._events_rel, data, what="attempt ledger")
        return event

    def events(self):
        """Every parseable event, in order. Corrupt lines are skipped and counted.

        A store whose root does not exist yet holds no events: a reader (status, freshness,
        a plan) must not create it and must not fail on it -- only a write creates the root.
        """
        sp = _sp()
        if not self.root.is_dir():
            return []
        raw = sp.confined_read_bytes(self.root, self._events_rel, what="attempt ledger",
                                     missing_ok=True)
        if not raw:
            return []
        out = []
        self.corrupt = 0
        for line in raw.decode("utf-8", "replace").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                self.corrupt += 1
                continue
            if not isinstance(obj, dict) or obj.get("v") != LEDGER_VERSION:
                self.corrupt += 1
                continue
            out.append(obj)
        return out

    # -- claims --

    def _claim_rel(self, task):
        sp = _sp()
        return f"{self.namespace}/{CLAIMS_DIR}/{sp.validate_id(task, 'task id')}.lock"

    def holder(self, task):
        """Who holds `task`'s claim -> dict or None. Unparseable is None (holds nothing)."""
        sp = _sp()
        if not self.root.is_dir():
            return None
        raw = sp.confined_read_bytes(self.root, self._claim_rel(task), what="attempt claim",
                                     missing_ok=True)
        if not raw:
            return None
        try:
            obj = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            return None
        return obj if isinstance(obj, dict) else None

    def claim(self, task, run):
        """Take `task` for `run` -> `{"stale_from": <previous holder or None>}`.

        The claim is a file created with `O_EXCL`, so two runs cannot both succeed. A claim
        whose process is gone is stale: it is unlinked and re-created, and because the
        re-creation is again `O_EXCL`, two runs racing to take over one stale claim still
        produce exactly one holder.
        """
        sp = _sp()
        rel = self._claim_rel(task)
        payload = json.dumps({"run": run, "pid": os.getpid(), "ts": utc_now()})
        _rt().ensure_private(self.root)
        try:
            sp.confined_create_bytes(self.root, rel, payload, what="attempt claim")
            self.append("claim.taken", run=run, task=task, stale_from=None)
            return {"stale_from": None}
        except sp.SafePathExists:
            pass
        previous = self.holder(task)
        if previous is not None and _pid_alive(previous.get("pid")):
            raise ClaimHeld(
                f"task {task} is claimed by run {previous.get('run')} (pid "
                f"{previous.get('pid')}, since {previous.get('ts')}); refusing to run it twice. "
                f"If that process is gone and its pid was recycled, clear the claim deliberately."
            )
        sp.confined_unlink(self.root, rel, what="attempt claim", missing_ok=True)
        try:
            sp.confined_create_bytes(self.root, rel, payload, what="attempt claim")
        except sp.SafePathExists:
            raise ClaimHeld(
                f"task {task}: another resuming run took over the stale claim first"
            ) from None
        self.append("claim.taken", run=run, task=task, stale_from=previous)
        return {"stale_from": previous}

    def release(self, task, run):
        """Drop `task`'s claim if `run` holds it -> whether it did."""
        sp = _sp()
        previous = self.holder(task)
        if previous is None or previous.get("run") != run:
            return False
        sp.confined_unlink(self.root, self._claim_rel(task), what="attempt claim",
                           missing_ok=True)
        self.append("claim.released", run=run, task=task)
        return True

    def break_claim(self, task, reason="operator"):
        """Clear `task`'s claim whoever holds it. An operator's deliberate act, recorded."""
        sp = _sp()
        previous = self.holder(task)
        sp.confined_unlink(self.root, self._claim_rel(task), what="attempt claim",
                           missing_ok=True)
        self.append("claim.broken", task=task, previous=previous, reason=reason)
        return previous

    # -- attempts --

    def record_started(self, run, task, op, model, prompt=None, verify_cmd=None,
                       artifact=None, acceptance_ref=None, policy_ref=None,
                       decision_ref=None, admission_ref=None, **extra):
        """Record an attempt BEFORE it is dispatched -> its attempt id.

        The prompt and verify command are stored as digests, so the ledger can say "the same
        prompt" or "the verify command changed" without carrying either text.

        The four `*_ref` arguments are the attempt's PROVENANCE (`PROVENANCE_REFS`): the
        acceptance criteria it was dispatched against, the policy bundle the run is pinned to,
        the decision record that produced the selection, and the budget grant that admitted it.
        Each is a `make_ref` pointer and each is optional -- a caller with none passes none, the
        field is not written at all, and `provenance` reads that back as unknown. They are
        correlated by the line they ride on: namespace, `run`, `task` and `attempt` are already
        there, so a reference needs no correlation key of its own. A grant in particular is
        minted BEFORE the attempt id exists, which is why it flows admission -> attempt and
        never the other way.
        """
        if op not in OPERATIONS:
            raise ValueError(f"attempt op must be one of {OPERATIONS}, got {op!r}")
        refs = validated_refs(acceptance_ref=acceptance_ref, policy_ref=policy_ref,
                              decision_ref=decision_ref, admission_ref=admission_ref)
        attempt = new_attempt_id()
        self.append(
            "attempt.started", run=run, task=task, attempt=attempt, op=op, model=model,
            prompt_sha=_sha(prompt), verify_sha=_sha(verify_cmd), artifact=artifact,
            **refs, **extra,
        )
        return attempt

    def record_finished(self, run, task, attempt, outcome, rc, output, cls=None,
                        duration_s=None, **extra):
        """Record how a dispatched attempt's PROCESS ended (not whether the task passed)."""
        report = bounded_tail(output, REPORT_CHARS)
        self.append(
            "attempt.finished", run=run, task=task, attempt=attempt, outcome=outcome, rc=rc,
            **{"class": cls}, report=report["text"], report_redactions=report["redactions"],
            duration_s=duration_s, **extra,
        )

    def record_verify(self, run, task, attempt, rc, output, artifact=None, **extra):
        """Record a verify result with its normalized signature and parsed failure count."""
        tail = bounded_tail(output, TAIL_CHARS)
        event = self.append(
            "verify.finished", run=run, task=task, attempt=attempt, rc=rc,
            signature=signature(output), failures=failure_count(output),
            tail=tail["text"], tail_redactions=tail["redactions"], artifact=artifact, **extra,
        )
        return event

    def record_projected(self, run, task, status, result=None, outcome_line=False, note="",
                         artifact=None, upstream=None, acceptance_ref=None, **extra):
        """Record that TASKS.md/NOTES.md now reflect the ledger (the projection happened).

        Step 24: `artifact` is the workspace fingerprint the verdict was reached on (the
        version of this task's output, when accepted), and `upstream` maps each dependency to
        the artifact version ITS latest acceptance carried, read at this moment. A later
        acceptance of an upstream task with a different artifact makes this task's evidence
        stale; `kit_contract.evidence_freshness` is the reader.

        `acceptance_ref` is the other half of that pair and answers the question `artifact`
        cannot: the artifact says which TREE the verdict was reached ON, this says which
        CRITERIA it was reached AGAINST. Optional and absent-means-unknown like every other
        reference, so every projection written before it existed still reads.
        """
        refs = validated_refs(acceptance_ref=acceptance_ref)
        self.append("task.projected", run=run, task=task, status=status, result=result,
                    outcome_line=bool(outcome_line), note=note, artifact=artifact,
                    upstream=upstream, **refs, **extra)

    def latest_acceptance(self, task):
        """The latest `done` projection with an outcome line, or None: the accepted version."""
        found = None
        for ev in self.events():
            if (ev.get("kind") == "task.projected" and ev.get("task") == task
                    and ev.get("status") == "done" and ev.get("outcome_line")):
                found = ev
        return found

    def latest_artifact(self, task):
        """The artifact version of `task`'s latest acceptance, or None when unrecorded."""
        acc = self.latest_acceptance(task)
        return acc.get("artifact") if acc else None

    def open_attempts(self, task=None):
        """Started attempts with no finish: a process died between dispatch and its record."""
        finished = set()
        started = []
        for ev in self.events():
            if ev.get("kind") == "attempt.finished":
                finished.add(ev.get("attempt"))
            elif ev.get("kind") == "attempt.started":
                if task is None or ev.get("task") == task:
                    started.append(ev)
        return [ev for ev in started if ev.get("attempt") not in finished]

    def reconcile_open(self, run, task, note):
        """Close every open attempt of `task` as `unknown` -> the attempt ids closed.

        Nothing is replayed. The attempt's allowance was consumed when it was granted, it
        stays consumed, and the closing record says why no result exists.
        """
        closed = []
        for ev in self.open_attempts(task):
            self.record_finished(
                run, task, ev["attempt"], OUTCOME_UNKNOWN, None, "", cls="unknown",
                reconciled_by=run, note=note,
            )
            closed.append(ev["attempt"])
        return closed

    def task_history(self, task):
        """Attempts of `task` in order, each joined with its finish and verify events."""
        by_id = {}
        order = []
        for ev in self.events():
            if ev.get("task") != task:
                continue
            kind = ev.get("kind")
            aid = ev.get("attempt")
            if kind == "attempt.started":
                by_id[aid] = {"attempt": aid, "run": ev.get("run"), "op": ev.get("op"),
                              "model": ev.get("model"), "started": ev, "finished": None,
                              "verify": None}
                order.append(aid)
            elif kind == "attempt.finished" and aid in by_id:
                by_id[aid]["finished"] = ev
            elif kind == "verify.finished" and aid in by_id:
                by_id[aid]["verify"] = ev
        return [by_id[a] for a in order]

    def latest_projection(self, task):
        found = None
        for ev in self.events():
            if ev.get("kind") == "task.projected" and ev.get("task") == task:
                found = ev
        return found

    def unprojected(self, task):
        """Attempts of `task` after its last outcome-line projection, oldest first.

        A finished attempt here with no projection is the crash-before-projection case: the
        work and its verdict exist, only the Markdown does not say so yet.
        """
        pending = []
        for ev in self.events():
            if ev.get("task") != task:
                continue
            kind = ev.get("kind")
            if kind == "attempt.started":
                pending.append(ev)
            elif kind == "task.projected" and ev.get("outcome_line"):
                pending = []
        return pending

    def usage(self):
        """Consuming operations not yet counted by a NOTES.md outcome line -> cap usage.

        Same keys and meanings as `kit_contract.count_plan_budget_usage`, so a driver adds the
        two: NOTES.md covers finished tasks, this covers the attempts nothing has projected --
        an interrupted ladder, a run that died after dispatch, an infrastructure stop that
        wrote no verdict. Once a task's outcome line is written (`task.projected` with
        `outcome_line`), its attempts up to that point are NOTES.md's to count.
        """
        uncovered = {}
        for ev in self.events():
            kind = ev.get("kind")
            task = ev.get("task")
            if kind == "attempt.started":
                uncovered.setdefault(task, []).append(ev.get("op"))
            elif kind == "task.projected" and ev.get("outcome_line"):
                uncovered.pop(task, None)
        used = {"max-dispatches": 0, "max-escalations": 0, "max-consults": 0,
                "max-model-calls": 0}
        for ops in uncovered.values():
            for op in ops:
                if op in ("initial", "retry", "escalation", "consult", "tick"):
                    used["max-dispatches"] += 1
                    used["max-model-calls"] += 1
                if op == "escalation":
                    used["max-escalations"] += 1
                if op == "consult":
                    used["max-consults"] += 1
                if op in ("review", "acceptance"):
                    used["max-model-calls"] += 1
        return used


def _sha(text):
    if text is None:
        return None
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


# ---- bounding and redaction ---------------------------------------------------------------------

def bounded_tail(text, limit):
    """The last `limit` characters of `text`, redacted -> `{"text", "redactions", "cut"}`.

    Tail, not head: a test runner's verdict is at the end. Redacted after cutting would be
    wrong for a key straddling the cut, so the cut is generous first and `redact` applies its
    own limit afterwards on the already-shortened text.
    """
    rd = _rd()
    text = text or ""
    cut = len(text) > limit
    piece = text[-limit:] if cut else text
    out = rd.redact(piece, limit=limit + 64)
    prefix = f"… [{len(text) - limit} earlier chars dropped]\n" if cut else ""
    return {"text": prefix + out["text"], "redactions": out["redactions"], "cut": cut}


# ---- failure classification ---------------------------------------------------------------------

_AUTH_RE = re.compile(
    r"(?i)(not logged in|unauthori[sz]ed|authentication (?:failed|required|error)|"
    r"invalid (?:api[ _-]?key|token|credentials?)|api[ _-]?key (?:is )?(?:invalid|missing|not set)|"
    r"token (?:has )?expired|login required|please (?:log|sign) in|\b401 unauthorized\b|"
    r"\b403 forbidden\b|no credentials|credentials (?:not found|missing|expired))"
)
_CONFIG_RE = re.compile(
    r"(?im)(unknown model|model [^\n]{1,60}?(?:not found|is not available|unavailable|does not exist)|"
    r"unrecognized arguments|unknown (?:flag|option|argument)|no such option|^usage: |"
    r"invalid choice|invalid value for|is not a valid|unsupported (?:effort|reasoning|value|model))"
)
_PERMISSION_RE = re.compile(
    r"(?i)(permission denied|operation not permitted|\bEACCES\b|\bEPERM\b|read-only file system|"
    r"sandbox (?:denied|violation))"
)
_INFRA_RE = re.compile(
    r"(?i)(command not found|connection (?:refused|reset|timed out)|network is unreachable|"
    r"\bECONNREFUSED\b|\bENOTFOUND\b|\bETIMEDOUT\b|rate limit|\b429\b|service unavailable|"
    r"\b503\b|\b502 bad gateway\b|overloaded|temporarily unavailable)"
)

_INFRA_OUTCOMES = ("missing-executable", "bad-workdir", "start-failed", "not-permitted",
                   "timeout", "cancelled")


def classify_dispatch(rc, output, proc_outcome=None):
    """Why a dispatch failed -> one of `CLASSES`, or None when it did not fail.

    Order matters and is deliberate: what the process runner observed beats what the output
    says (a timeout's output is whatever was flushed); an exit of zero is never a failure
    whatever the text contains; then the text is matched most-specific first, so "permission
    denied" on a credential file reads as permission, not as infrastructure.
    """
    if proc_outcome in _INFRA_OUTCOMES:
        return "infrastructure"
    if rc == 0:
        return None
    text = output or ""
    if _AUTH_RE.search(text):
        return "auth"
    if _CONFIG_RE.search(text):
        return "config"
    if _PERMISSION_RE.search(text):
        return "permission"
    if _INFRA_RE.search(text):
        return "infrastructure"
    if rc is not None and rc == _pr().INFRASTRUCTURE_RC:
        return "infrastructure"
    return "unknown"


def recovery_for(cls):
    """What to do about a failure of class `cls`: `escalate` or `stop`."""
    return RECOVERY.get(cls, "stop")


# ---- progress ---------------------------------------------------------------------------------------

_NORMALIZE = (
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"), "<ts>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), "<date>"),
    (re.compile(r"\b\d{1,2}:\d{2}:\d{2}(?:\.\d+)?\b"), "<time>"),
    (re.compile(r"\b\d+(?:\.\d+)?\s?(?:ms|s|sec|secs|seconds?|min|mins|minutes?)\b"), "<dur>"),
    (re.compile(r"0x[0-9a-fA-F]+"), "<addr>"),
    (re.compile(r"\b[0-9a-f]{12,}\b"), "<hex>"),
    (re.compile(r"/(?:private/)?(?:tmp|var/folders)/\S+"), "<tmp>"),
    (re.compile(r"(?i)\bpid[ =:]+\d+\b"), "pid=<n>"),
    (re.compile(r"(?i)\bport[ =:]+\d+\b"), "port=<n>"),
    (re.compile(r"[ \t]+"), " "),
)


def normalize_output(text):
    """`text` with the parts that change on every run replaced by placeholders.

    Timestamps, durations, addresses, long hex ids, temp paths, pids and ports go; counts and
    names stay, because "3 failed" turning into "2 failed" is exactly the signal to keep.
    """
    out = text or ""
    for pattern, replacement in _NORMALIZE:
        out = pattern.sub(replacement, out)
    lines = [ln.strip() for ln in out.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def signature(text):
    """A stable digest of a verify output's meaning, not its bytes."""
    return hashlib.sha256(normalize_output(text).encode("utf-8")).hexdigest()


_FAILURE_PATTERNS = (
    # unittest: FAILED (failures=2, errors=1)
    re.compile(r"FAILED \((?P<a>[^)]*)\)"),
    # pytest summary line
    re.compile(r"(?m)^=+ .*?\b(?P<n>\d+) failed\b.*?=+$"),
    # jest
    re.compile(r"Tests:\s+(?P<n>\d+) failed"),
    # mocha
    re.compile(r"\b(?P<n>\d+) failing\b"),
    # cargo
    re.compile(r"test result: FAILED\. \d+ passed; (?P<n>\d+) failed"),
)
_GO_FAIL_RE = re.compile(r"(?m)^--- FAIL:")
_GENERIC_FAIL_RE = re.compile(r"(?m)^(?:FAIL|ERROR)\b")


def failure_count(text):
    """How many failures the runner itself reported, or None when it printed no tally.

    Reads the runner's summary, never guesses from prose. Unknown stays None: a count that is
    not there is not zero.
    """
    text = text or ""
    for pattern in _FAILURE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        if "a" in m.groupdict() and m.group("a") is not None:
            total = 0
            for key in ("failures", "errors"):
                km = re.search(rf"{key}=(\d+)", m.group("a"))
                if km:
                    total += int(km.group(1))
            return total
        return int(m.group("n"))
    go = len(_GO_FAIL_RE.findall(text))
    if go:
        return go
    generic = len(_GENERIC_FAIL_RE.findall(text))
    if generic:
        return generic
    return None


def observation(rc, output, artifact=None):
    """One verify result as the shape `progress` compares."""
    return {"rc": rc, "signature": signature(output), "failures": failure_count(output),
            "artifact": artifact}


def progress(prev, cur):
    """Whether `cur` is progress over `prev` -> `{"progress": bool, "reason": str}`.

    In order: a passing verify is progress; fewer reported failures is progress and more or
    the same is not, whatever the log looks like; with no tally to read, a changed signature
    counts only if the tree changed too (or nobody could tell) -- an output that shifts while
    nothing was written is noise, not work.
    """
    if prev is None:
        return {"progress": True, "reason": "first observation"}
    if cur.get("rc") == 0 and prev.get("rc") != 0:
        return {"progress": True, "reason": "verify passes"}
    pf, cf = prev.get("failures"), cur.get("failures")
    if pf is not None and cf is not None:
        if cf < pf:
            return {"progress": True, "reason": f"failures {pf} -> {cf}"}
        if cf > pf:
            return {"progress": False, "reason": f"failures increased {pf} -> {cf}"}
        return {"progress": False, "reason": f"same failure count ({cf})"}
    if cur.get("signature") != prev.get("signature"):
        pa, ca = prev.get("artifact"), cur.get("artifact")
        if pa is not None and ca is not None and pa == ca:
            return {"progress": False, "reason": "output changed but the tree did not"}
        return {"progress": True, "reason": "failure signature changed"}
    return {"progress": False, "reason": "identical failure signature"}


# ---- workspace identity ---------------------------------------------------------------------------

def workspace_fingerprint(workspace):
    """A digest of what the tree holds beyond HEAD, or None when git cannot say.

    Bounded local reads: HEAD, the diff against it, and the names, sizes and mtimes of
    untracked files (their contents are not read; an untracked build directory could be
    anything). None is an honest answer -- a non-git workspace, a hung git -- and is recorded as
    such rather than replaced by a guess.
    """
    pr = _pr()
    ws = Path(workspace)

    def git(*args):
        try:
            return pr.run(["git", "-C", str(ws), *args], cwd=ws,
                          timeout=GIT_PROBE_TIMEOUT_SECONDS, name="git probe", text=False)
        except Exception:  # noqa: BLE001 -- a fingerprint is optional evidence
            return {"rc": 1, "stdout": b""}

    top = git("rev-parse", "--show-toplevel")
    if top["rc"] != 0:
        return None
    head = git("rev-parse", "HEAD")
    diff = git("diff", "--binary", "--no-ext-diff", "HEAD")
    status = git("status", "--porcelain=v1", "-z", "--untracked-files=all")
    if diff["rc"] != 0 or status["rc"] != 0:
        return None
    root = Path(top["stdout"].decode("utf-8", "replace").strip())
    meta = []
    for entry in status["stdout"].split(b"\0"):
        if not entry.startswith(b"?? "):
            continue
        rel = entry[3:]
        try:
            st = os.stat(root / rel.decode("utf-8", "surrogateescape"), follow_symlinks=False)
            meta.append(rel + b"\0" + str(st.st_size).encode() + b"\0" + str(st.st_mtime_ns).encode())
        except OSError:
            meta.append(rel + b"\0?")
    material = (head["stdout"].strip() if head["rc"] == 0 else b"") + b"\0" + diff["stdout"] \
        + b"\0" + status["stdout"] + b"\0" + b"\0".join(meta)
    return hashlib.sha256(material).hexdigest()


# ---- retry context ---------------------------------------------------------------------------------

#: Ceiling on the text fed into the next attempt. Well under any model's window; the point is
#: relevance, and a model given ten thousand lines of prior log reads none of them.
CONTEXT_CHARS = 4000


def retry_context(history, verify_cmd=None, limit=CONTEXT_CHARS, include_tail=True):
    """Bounded, redacted account of prior attempts for the next prompt -> str ("" if none).

    What the next attempt needs to know: how many tries there were and on what, what the last
    one did, what the check said and whether that is better or worse than before, and whether
    an attempt exists whose result nobody recorded. Not the full logs.

    `include_tail=False` omits the verify output itself, for a caller that already appends
    the immediate verify evidence and wants only the history beside it.
    """
    if not history:
        return ""
    lines = ["", "--- PRIOR ATTEMPTS (attempt ledger; bounded and redacted) ---"]
    summary = []
    for h in history:
        fin = h.get("finished") or {}
        ver = h.get("verify") or {}
        if fin.get("outcome") == OUTCOME_UNKNOWN:
            state = "outcome unknown -- the process left no result; the tree may carry its changes"
        elif fin.get("class") and fin.get("class") != "verification":
            state = f"dispatch failed ({fin.get('class')})"
        elif ver:
            state = f"verify exit {ver.get('rc')}"
        elif fin:
            state = "dispatched, not verified"
        else:
            state = "in flight"
        summary.append(f"{h.get('op')}@{h.get('model') or 'default'}: {state}")
    lines.append(f"attempts so far: {len(history)} ({'; '.join(summary)})")
    if verify_cmd:
        lines.append(f"verify: {verify_cmd}")
    # The diagnostics come from the most recent attempt that WAS verified; the most recent
    # attempt of all may be the one whose process died, which has nothing to show.
    verified = [h for h in history if h.get("verify")]
    last = verified[-1] if verified else None
    prev = verified[-2] if len(verified) > 1 else None
    if last is not None:
        lv = last["verify"]
        pv = (prev or {}).get("verify") or {}
        trend = ""
        if lv.get("failures") is not None and pv.get("failures") is not None:
            trend = f" (was {pv.get('failures')})"
        failures = "unknown" if lv.get("failures") is None else lv.get("failures")
        # Tree identity at each verify: the same digest means the attempt between them
        # wrote nothing that git can see.
        ls = lv.get("artifact")
        ps = pv.get("artifact") if pv else None
        if ls is None or ps is None:
            changed = "unknown"
        else:
            changed = "no" if ls == ps else "yes"
        lines.append(
            f"last verify exit: {lv.get('rc')}  failures: {failures}{trend}  "
            f"tree changed since the previous verified attempt: {changed}"
        )
        if include_tail and lv.get("tail"):
            lines.append("last verify output (tail):")
            lines.append(lv["tail"])
    reported = [h for h in history if (h.get("finished") or {}).get("report")]
    if reported:
        lines.append("last attempt's own report (tail):")
        lines.append(reported[-1]["finished"]["report"])
    text = "\n".join(lines)
    if len(text) > limit:
        text = text[:limit] + f"\n… [retry context cut at {limit} chars]"
    return text


# ---- CLI ----------------------------------------------------------------------------------------------

def _render_history(ledger, task):
    out = [f"## {ledger.namespace} / {task}"]
    for h in ledger.task_history(task):
        fin = h.get("finished") or {}
        ver = h.get("verify") or {}
        out.append(
            f"  {h['attempt']}  {h.get('op'):<10} model={h.get('model') or '-':<20} "
            f"outcome={fin.get('outcome') or 'open':<10} class={fin.get('class') or '-':<14} "
            f"verify_rc={ver.get('rc') if ver else '-'} failures={ver.get('failures') if ver else '-'}"
        )
    proj = ledger.latest_projection(task)
    if proj:
        out.append(f"  projected: status={proj.get('status')} result={proj.get('result')} "
                   f"outcome_line={proj.get('outcome_line')}")
    holder = ledger.holder(task)
    if holder:
        alive = _pid_alive(holder.get("pid"))
        out.append(f"  claim: run={holder.get('run')} pid={holder.get('pid')} "
                   f"({'alive' if alive else 'stale'})")
    return "\n".join(out)


def _demo():
    """A synthetic ledger in a temp dir: one task, an interrupted attempt, a resume. Spends
    nothing, spawns nothing."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        ledger = AttemptLedger(tmp, "demo-kit")
        run1 = "2026-01-01-0001"
        ledger.claim("T1", run1)
        a1 = ledger.record_started(run1, "T1", "initial", "fake-cheap", prompt="do it",
                                   verify_cmd="python3 -m unittest")
        ledger.record_finished(run1, "T1", a1, "ok", 0, "implemented the thing", cls=None)
        ledger.record_verify(run1, "T1", a1, 1,
                             "Ran 5 tests in 0.31s\n\nFAILED (failures=3)\n")
        a2 = ledger.record_started(run1, "T1", "escalation", "fake-mid", prompt="do it",
                                   verify_cmd="python3 -m unittest")
        # ... and the process dies here: a2 has no finish, and nobody released the claim.
        print("run 1 died after dispatching its escalation:")
        print(_render_history(ledger, "T1"))
        print()
        run2 = "2026-01-02-0002"
        ledger.release("T1", run1)  # the demo stands in for a dead pid
        ledger.claim("T1", run2)
        closed = ledger.reconcile_open(run2, "T1", "resumed by run 2; no result was recorded")
        print(f"run 2 resumes: closed {closed} as unknown; usage carried = {ledger.usage()}")
        prev = observation(1, "Ran 5 tests in 0.31s\n\nFAILED (failures=3)\n")
        noise = observation(1, "Ran 5 tests in 0.44s\n\nFAILED (failures=3)\n")
        better = observation(1, "Ran 5 tests in 0.29s\n\nFAILED (failures=1)\n")
        print(f"timestamp-only change -> {progress(prev, noise)}")
        print(f"fewer failures, similar log -> {progress(prev, better)}")
        print(f"missing CLI -> {classify_dispatch(124, 'x', proc_outcome='missing-executable')}"
              f" -> {recovery_for('infrastructure')}")
        print(f"logged out -> {classify_dispatch(1, 'Error: Not logged in. Run `login`.')}"
              f" -> {recovery_for('auth')}")
        print()
        print("retry context the next attempt would receive:")
        print(retry_context(ledger.task_history("T1"), verify_cmd="python3 -m unittest"))
    return 0


def _cli(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        prog="attempt_ledger.py",
        description="Inspect the attempt ledger (per-run dispatch/verify records). "
                    "`demo` is synthetic and writes only to a temp dir.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo", help="synthetic walkthrough in a temp dir; spends nothing")
    show = sub.add_parser("show", help="print a task's attempt history")
    show.add_argument("--store", required=True, help="ledger root (the attempts store)")
    show.add_argument("--namespace", required=True, help="kit slug or ralph-<hash>")
    show.add_argument("--task", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "demo":
        return _demo()
    ledger = AttemptLedger(args.store, args.namespace)
    print(_render_history(ledger, args.task))
    if ledger.corrupt:
        print(f"  ({ledger.corrupt} unparseable line(s) skipped)")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
