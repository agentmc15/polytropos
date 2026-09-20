#!/usr/bin/env python3
"""The evidence ONE decision had in front of it, frozen -- and the label lifecycle beside it.

    training_data.py status   [--json]   # is collection on, where would it write, what is wired
    training_data.py taxonomy [--json]   # the cause taxonomy, reconciled against the ledger's
    training_data.py demo     [--json]   # the whole seam over synthetic data in a temp dir

============================================================================================
 COLLECTION IS OFF, AND TWO DIFFERENT FACTS SAY SO
============================================================================================
`COLLECTION_ENABLED` is False: a fresh checkout collects nothing, and every entry point
re-derives it at call time rather than capturing it in a default argument. `CAPTURE_WIRED` is
False, which is a DIFFERENT fact: no production path calls the hook, so flipping the switch
alone still collects nothing because nothing invokes it. Turning collection on takes three
deliberate acts -- declare a `CollectionScope` with a purpose, a retention period, an owner
approval reference and `eligibility="approved"`; pass `enabled=True` (or flip the constant);
and wire `capture_hook` into a decision or attempt owner, which nobody has done. The precedent
for saying it this way is `workflow_eval.CONFINED_DISPATCH_WIRED` and
`improvement_loop.PROPOSER_WIRED`.

============================================================================================
 THIS IS NOT TRANSCRIPT LOGGING
============================================================================================
A snapshot is the bounded, allowlisted evidence a NAMED decision was taken on: the task
statement, the code context it was shown, the error it observed, the tool state, the
constraints. `INPUT_FIELDS` is closed and `MAX_ENTRIES_PER_FIELD`/`MAX_FIELD_CHARS` bound it,
so nothing here accumulates as a conversation goes on: there is no field a message could land
in, no append that is not one decision, and no path that reads a transcript, a harness home or
a session file. Every entry must name the instant it was observed and must place at or before
the decision -- an undated one is refused rather than assumed contemporaneous.

============================================================================================
 INPUT AND LABEL ARE DIFFERENT ARTIFACTS
============================================================================================
`tasks/kits/decision-improvement/TRAINING-DATA.md`: "Later reproduction or review may establish
a cause, but cannot alter the historical input snapshot." So the snapshot has NO label slot to
fill. `attach_label` returns the example unchanged -- byte-identical canonical form -- beside a
SEPARATE artifact that points at `input_sha`, and it refuses a label payload carrying an input
field at any depth. `example_id` is derived from `input_sha`, so one id can never name two
different inputs, and re-capturing identical evidence is idempotent rather than a second
example. The label LIFECYCLE is the section below `persist` -- `adjudicate`, `label_state`,
`attach_action`, `eligibility_state`, `revoke`, `export_eligibility` -- and every one of those
writes a separate artifact keyed by `example_id`: none of them has a route into a snapshot's
bytes, and `attach_label`'s own `status` is still `unadjudicated` with nothing able to change it
in place.

============================================================================================
 UNKNOWN IS UNKNOWN
============================================================================================
Absent is never zero and never inferred. A requested model does not populate the dispatched or
observed one; a missing usage record is not 0 tokens; an unknown sequence number is not 0. The
`unknown` list on every record names each gap by its dotted path, so a reader does not have to
tell "absent" from "zero" by guessing, and resource bases are kept apart and never summed.

============================================================================================
 WHAT THE REDACTOR DOES AND DOES NOT PROMISE
============================================================================================
Every free-text entry goes through `bin/redact.py` before it is persisted, and its findings
ride on the record as `{kind: count}` -- enough to see that something was caught, never enough
to reconstruct it. Shape-matching cannot prove absence: a password that looks like a word, a
customer name or an address has no shape and is not caught. No sentence here claims otherwise,
and the honest claim is field-level -- THESE fields, bounded to THIS length, with known
credential shapes labelled and the counts reported.

============================================================================================
 WHAT THIS MODULE IS NOT
============================================================================================
It is not a second ledger: `bin/attempt_ledger.py` owns dispatch events and this module only
POINTS at them, through that module's own `make_ref`. It is not a second validator of decision
objects: a question must arrive already parsed by `bin/decision_contract.py`. It is not a
second serializer: canonical bytes and duplicate-key-safe parsing are that contract's `dumps`
and `loads`. It is not a second path layer: every write goes through `bin/safe_paths.py` into a
root `bin/runtime_data.py` resolved. It is not a second label-source or attempt-result
vocabulary: `bin/decision_eval.py` owns both and `reconcile_label_sources` /
`reconcile_action_outcomes` read them at call time. It is not a second partition, grouping or
exposure authority: `bin/workflow_eval.py` owns all three and `dataset_rules` /
`verify_manifest` / `exposure_state` are read at call time. It IS the local exporter -- D33's
`build_dataset` / `write_dataset` / `read_dataset` produce deterministic JSONL plus an immutable
manifest under the same store seam -- and it is NOT a trainer: readiness is D34's, and no code
path here reaches a network, a provider, a model or a real harness home.
"""

import argparse
import dataclasses
import datetime
import hashlib
import importlib.util
import json
import re
import shutil
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

#: This record's own schema, registered in `release_gate.VERSION_SOURCES`. It versions the
#: SNAPSHOT -- not the ledger line that points at it, not the decision contract that validated
#: its question. A reader holding one of these needs to know which field names apply to IT.
SNAPSHOT_VERSION = "polytropos.training-snapshot/1"

#: The cause taxonomy's own version, registered separately for the same reason: the label
#: vocabulary can be revised without the record shape moving, and a stored example must say
#: which vocabulary its question was asked under.
TAXONOMY_VERSION = "polytropos.training-cause-taxonomy/1"

#: The `runtime_data` store this module -- and only this module -- writes.
STORE = "training"

#: Where snapshots land inside that store, one file per CAPTURE date.
SNAPSHOT_DIR = "snapshots"

# ---- the two switches, both off ---------------------------------------------------------------

#: Whether collection is on in this checkout. It is not. Every entry point reads this at call
#: time (`enabled=None` means "ask the constant now"), so nothing can hold a stale True and
#: nothing can be turned on by a default argument evaluated at import.
COLLECTION_ENABLED = False

#: Whether any production path calls `capture_hook`. None does. This is a separate fact from
#: the switch above: flipping `COLLECTION_ENABLED` collects nothing while no caller exists, and
#: wiring one has to be a visible edit here rather than an accident somewhere else.
CAPTURE_WIRED = False

COLLECTION_OFF_LABEL = (
    "collection is off: training_data.COLLECTION_ENABLED is False in a fresh checkout, and "
    "nothing was gathered, opened or written. Turning it on takes a declared CollectionScope "
    "with an approved eligibility, an explicit enabled=True, and a call site -- and "
    "training_data.CAPTURE_WIRED is False, so there is no call site")

NOT_WIRED_LABEL = (
    "no production path calls capture_hook: training_data.CAPTURE_WIRED is False. A green test "
    "proves this seam works; it does not prove anything invokes it")

REDACTION_LIMIT_NOTE = (
    "shape-matching redaction reports what it caught by kind and count; it cannot prove that "
    "no secret remains, because a secret with no distinctive shape has none to match")

LABEL_SEPARATE_NOTE = (
    "an input snapshot carries no label and has no slot for one. A cause established later is a "
    "separate artifact pointing at this example's input_sha; it can never alter these bytes")

NEVER_SUM_NOTE = (
    "resource bases are kept apart and never added: model-reported tokens, an estimate, a "
    "subscription proxy, credits and an unpriced run answer different questions")

SYNTHETIC_NOTE = (
    "synthetic fixture data in a temporary directory. It demonstrates the mechanics and is not "
    "evidence about a model, a dataset's sufficiency, or training readiness")

# ---- bounds -----------------------------------------------------------------------------------

#: Longest a single retained text entry may be. Over it, the entry is REFUSED rather than cut:
#: a training input silently halved is a corrupt example, and "bounded" must not come to mean
#: "quietly truncated". The redactor still bounds what it returns, belt and braces, because a
#: placeholder can be longer than what it replaced.
MAX_FIELD_CHARS = 2_000

#: How many entries one input field may carry. A decision was shown a handful of files, not a
#: directory; a field that could hold hundreds is a transcript by another name.
MAX_ENTRIES_PER_FIELD = 8

#: Longest a whole serialized record may be. Over it, the record is refused -- the same posture
#: `attempt_ledger.MAX_LINE_BYTES` takes, for the same reason: exceeding it means a caller
#: bypassed the per-field bounds.
MAX_RECORD_BYTES = 16 * 1024

MAX_LABEL_CHARS = 200
MAX_RESTRICTIONS = 16
MAX_RETENTION_DAYS = 3_650

# ---- the record's own vocabularies ------------------------------------------------------------

#: What a decision-time input may contain. CLOSED: a key nobody here reads is refused rather
#: than stored, so a caller cannot widen a snapshot into a log by passing another field.
INPUT_FIELDS = ("task_statement", "code_context", "observed_error", "tool_state", "constraints")

#: The keys one entry of an input field carries when a caller offers it.
ENTRY_KEYS = ("text", "observed_at", "source", "artifact_sha")

#: Reproducibility, exactly as `TRAINING-DATA.md` names it. `labeling_tooling` is always unknown
#: at capture time, because labelling has not happened yet and D32 owns it.
REPRODUCIBILITY_FIELDS = ("harness", "requested_model", "dispatched_model", "observed_model",
                          "prompt_version", "policy_version", "code_revision",
                          "capture_tooling", "labeling_tooling")

#: How complete the resource account is. `unknown` is the default and is not `complete`.
RESOURCE_COMPLETENESS = ("complete", "partial", "unknown")

#: Eligibility states this module can see. D32 owns the lifecycle that moves between them; what
#: lives here is the GATE: only `approved` may persist training content, and everything else --
#: including `unknown` -- fails closed with nothing written.
ELIGIBILITY_STATUSES = ("approved", "refused", "expired", "revoked", "unknown")

#: The one state that may be persisted as training content.
ELIGIBLE_TO_PERSIST = "approved"

#: Why a capture did not collect. A caller branches on these and a tally counts them, so they
#: are stable strings rather than prose.
SKIP_REASONS = ("collection-disabled", "no-collection-scope", "eligibility-not-approved",
                "refused")

#: The reference names a snapshot may carry beyond the ledger's own four. `attempt_ref` and
#: `task_ref` are this record's, because an attempt id and a task id are what join a snapshot
#: back to the run it came from; see `source_ref_names`, which refuses a collision.
EXTRA_SOURCE_REFS = ("attempt_ref", "task_ref")

#: At least one of these must be present: a snapshot nobody can trace back to the decision or
#: the attempt it describes is not evidence, it is an anecdote.
REQUIRED_SOURCE_ONE_OF = ("decision_ref", "attempt_ref")

#: The placement a retained input entry must have. The primitive is `decision_eval.placement`;
#: this names which of its answers is admissible, and the other two are refusals.
ADMISSIBLE_PLACEMENT = "at-or-before-prediction"

# ---- the cause taxonomy ----------------------------------------------------------------------

#: The adjudicated cause vocabulary `TRAINING-DATA.md` starts from. A ROOT CAUSE, never a
#: symptom: a nonzero test exit is not a member, because "the check failed" is what was observed
#: and not why.
CAUSE_CLASSES = ("environment-infrastructure", "missing-context", "implementation-error",
                 "configuration-permission", "multiple-causes", "unknown")

#: The members no operational signal can produce. Reaching one takes review evidence --
#: reproduction, a tool failure stage, an independent reader -- which is D32's work.
REVIEW_ONLY_CLASSES = ("missing-context", "implementation-error", "multiple-causes")

#: How an `attempt_ledger` class reads as a CANDIDATE cause. Candidate, not truth: the ledger
#: classified a dispatch from its exit status and its output, which is an observation.
#:
#: Two mappings are deliberately `unknown` rather than flattering. The ledger's `model` says
#: WHOSE problem a failure was -- it is the branch that escalates -- and not which cause; and
#: `verification` is a failing check, which is the symptom `TRAINING-DATA.md` says to keep
#: distinct from a cause. Mapping either onto `implementation-error` would manufacture a
#: training target out of a routing decision.
OPERATIONAL_TO_CANDIDATE = {
    "infrastructure": "environment-infrastructure",
    "auth": "configuration-permission",
    "config": "configuration-permission",
    "permission": "configuration-permission",
    "model": "unknown",
    "verification": "unknown",
    "unknown": "unknown",
}

#: The ledger classes that name a symptom or a routing branch rather than a cause. Recorded so a
#: reader of a candidate label knows which two arrived as `unknown` on purpose.
SYMPTOM_NOT_CAUSE = ("model", "verification")

#: The ledger classes `attempt_ledger.classify_dispatch` can never return. Read from its source
#: on 2026-09-19: it returns `infrastructure`, `auth`, `config`, `permission` or `unknown`, and
#: `None` when the dispatch did not fail. So an operational label for either of these came from
#: somewhere else -- a ladder decision, a verify result -- and a pipeline that expected
#: `classify_dispatch` to supply them would find those two classes always empty.
#: `tests/test_training_data.py` re-derives this by calling that function and by reading its
#: source, so the note cannot quietly outlive the behaviour.
NOT_PRODUCED_BY_DISPATCH = ("model", "verification")

CANDIDATE_LABEL_NOTE = (
    "a candidate cause derived from an operational class is an OBSERVATION, never an adjudicated "
    "target: the ledger classified a dispatch from its exit status and its output, and a "
    "supervised label needs review evidence instead")

# ---- sibling loaders (bin/ is not a package) --------------------------------------------------

_MODS = {}


def _sibling(name):
    if name not in _MODS:
        path = Path(__file__).resolve().parent / f"{name}.py"
        spec = importlib.util.spec_from_file_location(f"polytropos_td_{name}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _MODS[name] = mod
    return _MODS[name]


def _al():
    return _sibling("attempt_ledger")


def _contract():
    return _sibling("decision_contract")


def _de():
    return _sibling("decision_eval")


def _rd():
    return _sibling("redact")


def _rt():
    return _sibling("runtime_data")


def _sp():
    return _sibling("safe_paths")


def _wf():
    return _sibling("workflow_eval")


def _refuse(code, message):
    """One refusal, in the decision contract's vocabulary rather than a second one beside it."""
    return _contract().ContractError(code, message)


# ---- canonical form, borrowed rather than rebuilt ---------------------------------------------

def canonical(payload):
    """The bytes every digest here is taken over -- `decision_contract.dumps`, unchanged.

    Borrowed on purpose. Two canonicalisers in one repository are two answers to "what are
    these bytes", and a digest is only worth taking if everyone takes it the same way.
    """
    return _contract().dumps(payload)


def _sha(payload):
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def _copy(value):
    """A deep copy of JSON-shaped data.

    ONE copy, at the boundary where a caller's structure becomes a record's. D14 learned this
    the hard way: two defensive copies of the same fact mask each other, so neither can be
    shown to be load-bearing and removing either changes nothing a test can see.
    """
    if isinstance(value, Mapping):
        return {key: _copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_copy(item) for item in value]
    return value


# ---- the reconciliation with the ledger's own classes -----------------------------------------

def reconcile_operational_classes():
    """How `attempt_ledger.CLASSES` reads in this taxonomy -> the whole reconciliation.

    The mapping must be an EXACT PARTITION of the ledger's own tuple, read from the ledger at
    call time. A class the ledger adds and this module has no answer for would otherwise be
    silently dropped -- examples of it would simply never carry a candidate cause -- and a class
    this module maps that the ledger has removed would be a vocabulary nobody writes. Both
    refuse here instead, which makes changing the ledger's classification a deliberate edit in
    this file.
    """
    owner = tuple(_al().CLASSES)
    mapped = set(OPERATIONAL_TO_CANDIDATE)
    missing = sorted(set(owner) - mapped)
    extra = sorted(mapped - set(owner))
    if missing or extra:
        raise _refuse(
            "unknown-value",
            f"the operational reconciliation is no longer an exact partition of "
            f"attempt_ledger.CLASSES: unmapped {missing or 'none'}, unknown {extra or 'none'}. "
            f"That module owns the classification; this one owns how it reads as a candidate "
            f"cause, and a silent gap would mean examples with no candidate label at all")
    bad = sorted(v for v in OPERATIONAL_TO_CANDIDATE.values() if v not in CAUSE_CLASSES)
    if bad:
        raise _refuse("unknown-value",
                      f"the reconciliation maps onto {bad}, which are not cause classes")
    return {
        "taxonomy_v": TAXONOMY_VERSION,
        "classes": list(CAUSE_CLASSES),
        "review_only": list(REVIEW_ONLY_CLASSES),
        "operational_owner": "bin/attempt_ledger.py:CLASSES",
        "operational_classes": list(owner),
        "candidate_of": dict(sorted(OPERATIONAL_TO_CANDIDATE.items())),
        "symptom_not_cause": list(SYMPTOM_NOT_CAUSE),
        "not_produced_by_dispatch": list(NOT_PRODUCED_BY_DISPATCH),
        "note": CANDIDATE_LABEL_NOTE,
    }


def candidate_cause(operational_class):
    """One `attempt_ledger` class -> its candidate cause, or None for "no failure".

    `None` in means the dispatch did not fail (`classify_dispatch`'s own answer for a zero
    exit), and `None` out says so. Nothing here invents a cause for a success.
    """
    reconcile_operational_classes()
    if operational_class is None:
        return None
    if operational_class not in OPERATIONAL_TO_CANDIDATE:
        raise _refuse("unknown-value",
                      f"{operational_class!r} is not one of attempt_ledger.CLASSES")
    return OPERATIONAL_TO_CANDIDATE[operational_class]


# ---- the reference names, reconciled the same way ---------------------------------------------

def source_ref_names():
    """Every reference a snapshot may carry -> a sorted tuple.

    The four provenance names come from `attempt_ledger.PROVENANCE_REFS`, read at call time, so
    this module never holds its own copy of them. A collision between that tuple and
    `EXTRA_SOURCE_REFS` refuses: the day the ledger declares an `attempt_ref` of its own, the
    two definitions must be reconciled deliberately rather than one shadowing the other.
    """
    owner = tuple(_al().PROVENANCE_REFS)
    overlap = sorted(set(owner) & set(EXTRA_SOURCE_REFS))
    if overlap:
        raise _refuse(
            "duplicate-entry",
            f"attempt_ledger.PROVENANCE_REFS now declares {overlap}, which this module also "
            f"declares in EXTRA_SOURCE_REFS. One name, one owner: reconcile them here")
    return tuple(sorted(owner + EXTRA_SOURCE_REFS))


# ---- refusing a label that carries the input ---------------------------------------------------

def _alnum(text):
    return re.sub(r"[^a-z0-9]+", "", text.lower())


#: Key spellings that would put input-time evidence inside a later artifact. The structural
#: names are here beside the field names because `input`, `input_sha`, `question` and
#: `prediction_at` are equally the snapshot's, and a label that carried one of them would be
#: proposing a second version of the record it is supposed to point at.
_INPUT_SHAPED = frozenset(
    _alnum(name) for name in INPUT_FIELDS + ("input", "inputs", "input_sha", "question",
                                             "boundary", "prediction_at", "features")
)


def _is_input_shaped(key):
    if not isinstance(key, str):
        return False
    if _alnum(key) in _INPUT_SHAPED:
        return True
    return any(_alnum(part) in _INPUT_SHAPED for part in key.split("."))


def assert_no_input_field(value, where="the label"):
    """Refuse a structure that carries input-time evidence under any key, at any depth.

    THE ROUTE THIS GUARDS IS REAL. `attach_label`'s payload is the caller's own object with the
    caller's own keys, and D32 is the task that gives it a schema. A label that arrives with a
    `task_statement`, or with an `evidence: {"observed_error": ...}` two levels down, is a
    second copy of the input written after the fact -- exactly what `TRAINING-DATA.md` forbids,
    and exactly the defect D14 had to fix when a field populated from what followed was
    presented as what the decision produced.

    IT REFUSES WHAT IT CANNOT WALK, AND WHAT IS NOT JSON. `_walk_keys` is the shared walker and
    it refuses rather than descends: a container it does not enter inspects nothing and certifies
    everything, so bytes, a set, a view, a generator and any other object are refusals rather
    than passes, and a namedtuple is refused although it IS a tuple.

    WHAT IT DOES NOT PROVE. This matches KEY spellings. A label that writes the task statement
    into a VALUE under an innocent key is not caught here -- what stops that one is the
    separation of artifacts: the example's bytes are digested and never rewritten, so whatever a
    label says, the input it points at is still the input.
    """
    keys, unwalkable = _walk_keys(value)
    hits = [key for key in keys if _is_input_shaped(key)]
    _refuse_keys(hits, unwalkable, where,
                 f"which is input-time evidence. {LABEL_SEPARATE_NOTE}")
    return value


# ---- primitives --------------------------------------------------------------------------------

def _mapping(value, where):
    if not isinstance(value, Mapping):
        raise _refuse("wrong-type", f"{where} must be an object, not {type(value).__name__}")
    return dict(value)


def _closed(value, keys, where):
    payload = _mapping(value, where)
    unknown = sorted(set(payload) - set(keys))
    if unknown:
        raise _refuse(
            "unknown-field",
            f"{where} carries {', '.join(repr(u) for u in unknown)}; the allowlist is "
            f"{', '.join(keys)}. A field nobody here reads is refused rather than stored -- "
            f"widening a snapshot is how it becomes a log")
    return payload


def _label_text(value, where, *, limit=MAX_LABEL_CHARS, optional=False):
    if value is None:
        if optional:
            return None
        raise _refuse("missing-field", f"{where} is required")
    if not isinstance(value, str) or not value.strip():
        raise _refuse("value-invalid", f"{where} must be a non-empty string, got {value!r}")
    text = value.strip()
    if len(text) > limit:
        raise _refuse("bounds-exceeded",
                      f"{where} is {len(text)} chars, past the {limit} this record holds")
    return text


def _one_of(value, allowed, where):
    if value not in allowed:
        raise _refuse("unknown-value",
                      f"{where} must be one of {', '.join(map(str, allowed))}, got {value!r}")
    return value


def _count(value, where, *, maximum, optional=True):
    if value is None:
        if optional:
            return None
        raise _refuse("missing-field", f"{where} is required")
    if isinstance(value, bool) or not isinstance(value, int):
        raise _refuse("wrong-type", f"{where} must be an int, not {type(value).__name__}")
    if value < 0 or value > maximum:
        raise _refuse("bounds-exceeded", f"{where}={value} is outside 0..{maximum}")
    return value


def _instant(value, where):
    """A timestamp this module will place in time, or a refusal.

    `decision_eval.placement` is the placement primitive and it answers `unknown-time` for
    anything it cannot read. That answer is fine for a report and useless for a training input,
    so an unreadable instant is refused HERE, before it can become an entry whose availability
    nobody can establish.
    """
    text = _label_text(value, where)
    if _de().placement(text, text) != ADMISSIBLE_PLACEMENT:
        raise _refuse(
            "value-invalid",
            f"{where}={text!r} names no instant this module will place: pass ISO-8601 with a "
            f"zone. A zoneless stamp would be read against the reader's own machine, which is "
            f"how a fact lands on the wrong side of the decision it is supposed to precede")
    return text


def _digest_or_none(value, where):
    if value is None:
        return None
    text = _label_text(value, where)
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise _refuse("value-invalid",
                      f"{where} must be a sha256 hex digest or absent, got {text!r}")
    return text


# ---- the collection scope ----------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class CollectionScope:
    """What an operator declared before anything could be collected.

    Frozen, and every field required except `source_restrictions`, because each one is a thing
    `TRAINING-DATA.md` says must be declared BEFORE capture rather than decided afterwards: the
    permitted purpose, how long the records may be kept, who approved it, and the eligibility
    state -- which must be `approved` for a single byte of training content to be persisted.
    """

    purpose: str
    retention_days: int
    eligibility: str
    approval_ref: tuple
    source_restrictions: tuple = ()

    def to_payload(self):
        return {
            "purpose": self.purpose,
            "retention_days": self.retention_days,
            "eligibility": self.eligibility,
            "approval_ref": dict(self.approval_ref),
            "source_restrictions": list(self.source_restrictions),
        }


def collection_scope(*, purpose, retention_days, eligibility="unknown", approval_ref=None,
                     source_restrictions=()):
    """Validate a declared collection scope -> a frozen `CollectionScope`.

    `eligibility` defaults to `unknown`, which is a scope that CANNOT persist training content.
    That default is the fail-closed one: a caller who did not say what they were allowed to
    collect has not said `approved`.
    """
    status = _one_of(eligibility, ELIGIBILITY_STATUSES, "the scope's eligibility")
    text = _label_text(purpose, "the scope's purpose", limit=MAX_FIELD_CHARS)
    if len(text.split()) < 3:
        raise _refuse("value-invalid",
                      f"the scope's purpose is {len(text.split())} word(s); a permitted purpose "
                      f"has to say what the data may be used for, not label it")
    days = _count(retention_days, "the scope's retention_days", maximum=MAX_RETENTION_DAYS,
                  optional=False)
    if days < 1:
        raise _refuse("value-invalid",
                      "the scope's retention_days must be at least 1: a retention period of "
                      "zero days is not a policy, it is an unanswered question")
    if approval_ref is None:
        raise _refuse("missing-field",
                      "the scope names no owner approval. Approval is a reference to something "
                      "that exists -- see attempt_ledger.make_ref -- and an unattributed scope "
                      "cannot be withdrawn by whoever granted it")
    ref = _al().read_ref(approval_ref)
    if ref is None:
        raise _refuse("not-a-reference",
                      f"the scope's approval_ref must come from attempt_ledger.make_ref, got "
                      f"{approval_ref!r}")
    if isinstance(source_restrictions, (str, bytes)):
        raise _refuse("wrong-type",
                      "source_restrictions is a sequence of restrictions, not one string")
    restrictions = tuple(_label_text(item, "a source restriction")
                         for item in tuple(source_restrictions))
    if len(restrictions) > MAX_RESTRICTIONS:
        raise _refuse("bounds-exceeded",
                      f"{len(restrictions)} source restrictions, past {MAX_RESTRICTIONS}")
    return CollectionScope(purpose=text, retention_days=days, eligibility=status,
                           approval_ref=tuple(sorted(ref.items())),
                           source_restrictions=restrictions)


def collection_state(*, scope=None, enabled=None):
    """Whether anything may be collected right now -> `{"collecting", "reason", "eligibility"}`.

    `enabled=None` re-derives `COLLECTION_ENABLED` AT CALL TIME. It is not a default argument
    value, because a module-level constant captured in a signature is evaluated once at import
    and would keep answering True after somebody turned collection back off.

    Three independent locks, checked in the order an operator would open them: the switch, a
    declared scope, and that scope's eligibility. The reason names the FIRST one shut, so a
    report says which act is missing rather than that something was wrong.
    """
    switch = COLLECTION_ENABLED if enabled is None else bool(enabled)
    if not switch:
        return {"collecting": False, "reason": "collection-disabled",
                "eligibility": None, "note": COLLECTION_OFF_LABEL}
    if scope is None:
        return {"collecting": False, "reason": "no-collection-scope", "eligibility": None,
                "note": "collection needs a declared scope: purpose, retention, approval"}
    if not isinstance(scope, CollectionScope):
        raise _refuse("wrong-type",
                      f"a collection scope comes from training_data.collection_scope, got "
                      f"{type(scope).__name__}")
    if scope.eligibility != ELIGIBLE_TO_PERSIST:
        return {"collecting": False, "reason": "eligibility-not-approved",
                "eligibility": scope.eligibility,
                "note": (f"eligibility is {scope.eligibility!r}; only "
                         f"{ELIGIBLE_TO_PERSIST!r} may be persisted as training content, and "
                         f"unknown use rights fail closed")}
    return {"collecting": True, "reason": None, "eligibility": scope.eligibility, "note": None}


# ---- input entries ------------------------------------------------------------------------------

def _entry(value, field, index, prediction_at):
    """One retained piece of input-time evidence, redacted and placed."""
    where = f"input.{field}[{index}]"
    payload = _closed(value, ENTRY_KEYS, where)
    raw = payload.get("text")
    if not isinstance(raw, str) or not raw.strip():
        raise _refuse("value-invalid", f"{where}.text must be a non-empty string")
    if len(raw) > MAX_FIELD_CHARS:
        raise _refuse(
            "bounds-exceeded",
            f"{where}.text is {len(raw)} chars, past the {MAX_FIELD_CHARS} a retained field "
            f"holds. It is refused rather than truncated: an example cut in half is a corrupt "
            f"example, and the caller decides what the decision actually saw")
    observed_at = _instant(payload.get("observed_at"), f"{where}.observed_at")
    placement = _de().placement(observed_at, prediction_at)
    if placement != ADMISSIBLE_PLACEMENT:
        raise _refuse(
            "value-invalid",
            f"{where} was observed {observed_at} and the decision was taken {prediction_at}, so "
            f"it places {placement!r}. Only {ADMISSIBLE_PLACEMENT!r} evidence may enter an "
            f"input: a later patch, a reviewer's diagnosis or a future test result was not "
            f"available when the decision was made")
    cleaned = _rd().redact(raw, limit=MAX_FIELD_CHARS)
    return {
        "text": cleaned["text"],
        "observed_at": observed_at,
        "placement": placement,
        "provenance": {
            "source": _label_text(payload.get("source"), f"{where}.source"),
            "artifact_sha": _digest_or_none(payload.get("artifact_sha"),
                                           f"{where}.artifact_sha"),
        },
        "redactions": dict(sorted(cleaned["redactions"].items())),
        "truncated": bool(cleaned["truncated"]),
        "original_length": cleaned["original_length"],
    }


def _input_block(value, prediction_at):
    """The whole input, allowlisted -> `(block, redaction totals, truncations)`.

    A field nobody offered is `None` and is named in the record's `unknown`. It is never `[]`:
    an empty list reads as "the decision was shown no code context", and absent reads as
    "nobody recorded what it was shown". Those are different facts.
    """
    payload = _closed({} if value is None else value, INPUT_FIELDS, "input")
    block = {}
    totals = {}
    truncated = 0
    for field in INPUT_FIELDS:
        offered = payload.get(field)
        if offered is None:
            block[field] = None
            continue
        if isinstance(offered, (str, bytes, Mapping)):
            raise _refuse("wrong-type",
                          f"input.{field} is a list of entries, each with "
                          f"{', '.join(ENTRY_KEYS)}; got {type(offered).__name__}")
        entries = list(offered)
        if not entries:
            raise _refuse("value-invalid",
                          f"input.{field} is an empty list. Omit the field for 'nobody recorded "
                          f"it'; an empty list claims the decision was shown none")
        if len(entries) > MAX_ENTRIES_PER_FIELD:
            raise _refuse("bounds-exceeded",
                          f"input.{field} carries {len(entries)} entries, past the "
                          f"{MAX_ENTRIES_PER_FIELD} a bounded snapshot holds")
        built = [_entry(item, field, index, prediction_at)
                 for index, item in enumerate(entries)]
        for entry in built:
            for kind, count in entry["redactions"].items():
                totals[kind] = totals.get(kind, 0) + count
            truncated += 1 if entry["truncated"] else 0
        block[field] = built
    if all(block[field] is None for field in INPUT_FIELDS):
        raise _refuse("missing-field",
                      "the snapshot carries no input at all. A decision-time snapshot is the "
                      "evidence the decision had in front of it; with none there is nothing to "
                      "learn from and nothing to store")
    return block, dict(sorted(totals.items())), truncated


# ---- the other blocks ---------------------------------------------------------------------------

def _sources(value):
    """The references this snapshot joins back on -> `(block, gaps)`."""
    names = source_ref_names()
    payload = _closed({} if value is None else value, names, "sources")
    block = {}
    gaps = {}
    for name in names:
        offered = payload.get(name)
        if offered is None:
            block[name] = None
            gaps[name] = sorted(_al().REF_FIELDS)
            continue
        ref = _al().read_ref(offered)
        if ref is None:
            raise _refuse("not-a-reference",
                          f"sources.{name} must come from attempt_ledger.make_ref -- an id, "
                          f"optionally the content digest and the referenced contract's "
                          f"version -- got {offered!r}")
        block[name] = dict(ref)
        gaps[name] = _al().ref_gaps(ref)
    if not any(block.get(name) for name in REQUIRED_SOURCE_ONE_OF):
        raise _refuse(
            "missing-field",
            f"the snapshot names neither {' nor '.join(REQUIRED_SOURCE_ONE_OF)}. An example "
            f"nobody can trace back to the decision or the attempt it describes cannot be "
            f"audited, revoked, or joined to its outcome")
    return block, {name: gap for name, gap in sorted(gaps.items()) if gap}


def _boundary(value):
    payload = _closed({} if value is None else value, ("sequence", "event"), "boundary")
    return {
        "sequence": _count(payload.get("sequence"), "boundary.sequence", maximum=2 ** 31),
        "event": _label_text(payload.get("event"), "boundary.event", optional=True),
        "rule": ADMISSIBLE_PLACEMENT,
    }


def _question(spec):
    """The exact question this decision asked -> its payload plus the schema versions.

    Deliberately refuses a raw dict, for the reason D14 gives: `bin/decision_contract.py` is
    the validator of question shapes, and a snapshot that accepted a payload directly would be
    validating them a second time in a module whose job is to store them. The duck type is on
    purpose too -- `bin/` is not a package, two loaders produce two unrelated classes, and an
    `isinstance` check here would refuse a valid spec for having been parsed by the other copy.
    """
    maker = getattr(spec, "to_payload", None)
    digester = getattr(spec, "digest", None)
    if not callable(maker) or not callable(digester) or isinstance(spec, Mapping):
        raise _refuse(
            "wrong-type",
            "the question must be a QuestionSpec already parsed by "
            "bin/decision_contract.py:parse_question, not a raw payload: an id is a handle and "
            "this record has to carry the complete wording and rubric that were asked")
    payload = maker()
    if not isinstance(payload, dict):
        raise _refuse("wrong-type", "the question did not produce a payload object")
    return {
        "spec": _copy(payload),
        "qualified_id": f"{payload.get('id')}@{payload.get('version')}",
        "digest": digester(),
        "schema_v": _contract().CONTRACT_VERSION,
        "taxonomy_v": TAXONOMY_VERSION,
    }


def _reproducibility(value):
    payload = _closed({} if value is None else value, REPRODUCIBILITY_FIELDS, "reproducibility")
    if payload.get("labeling_tooling") is not None:
        raise _refuse(
            "value-invalid",
            "reproducibility.labeling_tooling is unknown at capture time: labelling has not "
            "happened yet, and the tool that eventually does it is recorded on the LABEL "
            "artifact. Filling it in here would date a label to the moment of capture")
    block = {}
    for name in REPRODUCIBILITY_FIELDS:
        block[name] = _label_text(payload.get(name), f"reproducibility.{name}", optional=True)
    return block


def _resources(value):
    """Usage, time and review effort, each kept to its own basis.

    Bases are `decision_eval.RESOURCE_BASES`, read at call time from the module that owns that
    vocabulary. An absent basis is ABSENT -- not zero -- and nothing here adds two of them
    together, because a model-reported token count, an estimate, a subscription proxy, credits
    and an unpriced run are answers to different questions.
    """
    payload = _closed({} if value is None else value,
                      ("usage", "elapsed_seconds", "review_effort", "completeness"), "resources")
    bases = tuple(_de().RESOURCE_BASES)
    usage = payload.get("usage")
    if usage is None:
        by_basis = None
    else:
        offered = _mapping(usage, "resources.usage")
        unknown = sorted(set(offered) - set(bases))
        if unknown:
            raise _refuse("unknown-field",
                          f"resources.usage carries {', '.join(map(repr, unknown))}; the bases "
                          f"are {', '.join(bases)} (decision_eval.RESOURCE_BASES)")
        if not offered:
            raise _refuse("value-invalid",
                          "resources.usage is empty. Omit it for 'no usage record was kept'; an "
                          "empty account reads as a run that consumed nothing")
        by_basis = {}
        for basis in bases:
            if basis not in offered:
                continue
            amount = offered[basis]
            if isinstance(amount, bool) or not isinstance(amount, (int, float)):
                raise _refuse("wrong-type",
                              f"resources.usage[{basis!r}] must be a number, not "
                              f"{type(amount).__name__}")
            if amount != amount or amount in (float("inf"), float("-inf")) or amount < 0:
                raise _refuse("value-invalid",
                              f"resources.usage[{basis!r}]={amount!r} is not a finite "
                              f"non-negative quantity")
            by_basis[basis] = amount
    elapsed = payload.get("elapsed_seconds")
    if elapsed is not None:
        if isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)):
            raise _refuse("wrong-type", "resources.elapsed_seconds must be a number")
        if elapsed != elapsed or elapsed < 0:
            raise _refuse("value-invalid",
                          f"resources.elapsed_seconds={elapsed!r} is not a finite "
                          f"non-negative duration")
    review = payload.get("review_effort")
    if review is not None:
        review = _mapping(review, "resources.review_effort")
        review = {_label_text(k, "a review effort key"): _count(v, f"review_effort[{k!r}]",
                                                                maximum=2 ** 31)
                  for k, v in sorted(review.items())}
    return {
        "usage": by_basis,
        "elapsed_seconds": elapsed,
        "review_effort": review,
        "completeness": _one_of(payload.get("completeness") or "unknown",
                                RESOURCE_COMPLETENESS, "resources.completeness"),
        "note": NEVER_SUM_NOTE,
    }


def _eligibility(scope, captured_at):
    """The scope, as it stood at capture, plus the expiry its retention implies."""
    payload = scope.to_payload()
    try:
        expires = (datetime.date.fromisoformat(captured_at[:10])
                   + datetime.timedelta(days=scope.retention_days)).isoformat()
    except ValueError:
        expires = None
    return {
        "status": payload["eligibility"],
        "purpose": payload["purpose"],
        "retention_days": payload["retention_days"],
        "expires_on": expires,
        "approval_ref": payload["approval_ref"],
        "source_restrictions": payload["source_restrictions"],
        "redaction_status": "shape-matched",
    }


# ---- the snapshot -------------------------------------------------------------------------------

def _unknown_paths(record):
    """Every field this record cannot answer -> a sorted list of dotted names.

    The whole point of the list: a reader never has to tell "absent" from "zero" by guessing,
    and nothing downstream may treat a gap as a measurement. `label` is always on it, because a
    snapshot is an input and an input has no label.
    """
    out = ["label"]
    for field in INPUT_FIELDS:
        if record["input"][field] is None:
            out.append(f"input.{field}")
    for name in REPRODUCIBILITY_FIELDS:
        if record["reproducibility"][name] is None:
            out.append(f"reproducibility.{name}")
    for name in ("usage", "elapsed_seconds", "review_effort"):
        if record["resources"][name] is None:
            out.append(f"resources.{name}")
    if record["resources"]["completeness"] == "unknown":
        out.append("resources.completeness")
    for name in ("sequence", "event"):
        if record["boundary"][name] is None:
            out.append(f"boundary.{name}")
    for name, gap in record["source_gaps"].items():
        if record["sources"][name] is None:
            out.append(f"sources.{name}")  # the whole pointer is absent, not three parts of it
            continue
        for part in gap:
            out.append(f"sources.{name}.{part}")
    return sorted(set(out))


def snapshot(*, question, prediction_at, sources, scope, captured_at, input=None,
             boundary=None, reproducibility=None, resources=None, operational_class=None):
    """One decision-time snapshot -> an immutable record. Raises on anything unsafe.

    `captured_at` dates the record by CAPTURE, never by the decision it describes: a record is
    dated when it was written, and `prediction_at` separately says when the decision was taken.
    A snapshot taken late about a source that still exists is fine; one reconstructed from prose
    is not, and nothing here can produce one -- every field comes from a caller who had the
    artifact in hand, with the instant it was observed and the digest it had.

    `scope` must be an eligible `CollectionScope`. This function builds the training content, so
    it refuses to build any for a scope that is not `approved`: unknown use rights fail closed
    HERE, before there is a payload for anything to persist.

    Two digests, over different things. `input_sha` covers exactly the input-time evidence --
    the input, the question, the boundary, the sources and the prediction instant -- and is what
    a later label points at. `content_sha` covers the whole record. A label changing nothing
    about the input is therefore checkable rather than promised.
    """
    if not isinstance(scope, CollectionScope):
        raise _refuse("wrong-type",
                      f"a collection scope comes from training_data.collection_scope, got "
                      f"{type(scope).__name__}")
    if scope.eligibility != ELIGIBLE_TO_PERSIST:
        raise _refuse(
            "value-invalid",
            f"the collection scope's eligibility is {scope.eligibility!r}. Only "
            f"{ELIGIBLE_TO_PERSIST!r} may become training content; unknown, refused, expired "
            f"and revoked all fail closed, and no snapshot is built for them")
    captured = _instant(captured_at, "captured_at")
    predicted = _instant(prediction_at, "prediction_at")
    block, redactions, truncations = _input_block(input, predicted)
    source_block, gaps = _sources(sources)
    immutable = {
        "input": block,
        "question": _question(question),
        "boundary": _boundary(boundary),
        "sources": source_block,
        "prediction_at": predicted,
    }
    input_sha = _sha(immutable)
    record = {
        "v": SNAPSHOT_VERSION,
        "example_id": f"ex-{input_sha[:16]}",
        "example_id_basis": "input-sha",
        "captured_at": captured,
        "prediction_at": predicted,
        "boundary": immutable["boundary"],
        "sources": source_block,
        "source_gaps": gaps,
        "question": immutable["question"],
        "input": block,
        "input_sha": input_sha,
        "candidate_cause": {
            "class": candidate_cause(operational_class),
            "from_operational": operational_class,
            "taxonomy_v": TAXONOMY_VERSION,
            "adjudicated": False,
            "note": CANDIDATE_LABEL_NOTE,
        },
        "reproducibility": _reproducibility(reproducibility),
        "resources": _resources(resources),
        "eligibility": _eligibility(scope, captured),
        "redaction": {
            "redactions": redactions,
            "truncated": truncations,
            "note": REDACTION_LIMIT_NOTE,
        },
        "label_note": LABEL_SEPARATE_NOTE,
        "disclosures": [LABEL_SEPARATE_NOTE, REDACTION_LIMIT_NOTE, NEVER_SUM_NOTE,
                        CANDIDATE_LABEL_NOTE, NOT_WIRED_LABEL],
    }
    record["unknown"] = _unknown_paths(record)
    record["content_sha"] = _sha({k: v for k, v in record.items() if k != "content_sha"})
    size = len(canonical(record).encode("utf-8"))
    if size > MAX_RECORD_BYTES:
        raise _refuse(
            "bounds-exceeded",
            f"the record serializes to {size} bytes, past the {MAX_RECORD_BYTES} one snapshot "
            f"holds. Exceeding it means the per-field bounds were bypassed, so it is refused "
            f"rather than written")
    return record


def integrity(record):
    """Recompute both digests -> `{"input_sha_ok", "content_sha_ok", "example_id_ok"}`.

    A digest IDENTIFIES content; it is not protection against a worker that can rewrite the
    file. What this catches is a record whose input was edited after it was written -- which is
    exactly the failure "exact input-time evidence is immutable" has to be checkable against.
    """
    if not isinstance(record, Mapping) or record.get("v") != SNAPSHOT_VERSION:
        raise _refuse("not-a-reference", f"this is not a {SNAPSHOT_VERSION} record")
    immutable = {
        "input": record.get("input"),
        "question": record.get("question"),
        "boundary": record.get("boundary"),
        "sources": record.get("sources"),
        "prediction_at": record.get("prediction_at"),
    }
    input_sha = _sha(immutable)
    body = {k: v for k, v in record.items() if k != "content_sha"}
    return {
        "input_sha_ok": input_sha == record.get("input_sha"),
        "content_sha_ok": _sha(body) == record.get("content_sha"),
        "example_id_ok": record.get("example_id") == f"ex-{input_sha[:16]}",
        "recomputed_input_sha": input_sha,
    }


def assert_intact(record, where="the stored record"):
    report = integrity(record)
    broken = sorted(name for name, ok in report.items()
                    if name.endswith("_ok") and not ok)
    if broken:
        raise _refuse("value-invalid",
                      f"{where} fails {', '.join(broken)}: its bytes are not the bytes that "
                      f"were digested, so it is not the evidence it claims to be")
    return record


# ---- the late label, which is a different artifact ---------------------------------------------

def attach_label(record, payload):
    """A label arriving later -> `{"example", "label"}`, with `example` untouched.

    THE POINT OF THIS FUNCTION IS WHAT IT REFUSES. It cannot write into the snapshot: the
    example it returns is a copy whose canonical bytes are asserted equal to the original's, the
    label is a separate object carrying only `example_id` and `input_sha`, and a payload holding
    input-time evidence at any depth is refused by `assert_no_input_field`.

    IT IS NOT THE ADJUDICATION. What comes out of here is `status: "unadjudicated"` with the
    payload quoted verbatim under `claim`, and nothing can advance THIS object: a review produces
    a new `adjudication` artifact through `adjudicate`, which weighs evidence and leaves this one
    exactly as it was. A provider's or a reviewer's opinion recorded here is a candidate, never
    independently verified truth.
    """
    assert_intact(record, "the record being labelled")
    before = canonical({k: v for k, v in record.items() if k != "content_sha"})
    assert_no_input_field(payload, "the label payload")
    if not isinstance(payload, Mapping) or not payload:
        raise _refuse("value-invalid", "a label payload is a non-empty object")
    example = _copy(dict(record))
    after = canonical({k: v for k, v in example.items() if k != "content_sha"})
    if before != after:
        raise _refuse("value-invalid",
                      "labelling changed the example's bytes, which is the one thing it may "
                      "never do")
    label = {
        "example_id": record["example_id"],
        "input_sha": record["input_sha"],
        "taxonomy_v": TAXONOMY_VERSION,
        "status": "unadjudicated",
        "claim": _copy(dict(payload)),
        "note": ("a claim about this example, recorded beside it and never inside it. Review, "
                 "correction history and adjudication are D32's; nothing here verifies it"),
    }
    return {"example": example, "label": label}


# ---- persistence ---------------------------------------------------------------------------------

def default_store(repo_root, env=None):
    """Where snapshots live unless a `--store-dir` flag says otherwise.

    `bin/runtime_data.py` resolves it, as it does for every other store: a per-user
    application-data directory namespaced per checkout, 0700/0600, never a hardcoded path under
    this tree -- which is distributed, cached and often cloud-synced. `training` is a row in
    that module's `STORES`, so `where`/`migrate`/`export`/`forget` see it, the packaging gate
    checks its ignore rule, and `tests/test_privacy_layout.py` covers it.
    """
    return _rt().store_path(STORE, repo_root, env=env)


def _day_rel(captured_at):
    """`snapshots/<capture date>.jsonl`, with the date validated as a filename component.

    Checked here rather than trusted: the date comes out of a caller's timestamp, and a string
    that can name a path is a string that can leave the directory it was meant to stay in.
    """
    day = _sp().validate_id(str(captured_at)[:10], "a capture date")
    return f"{SNAPSHOT_DIR}/{day}.jsonl"


def read_snapshots(store_dir, captured_at):
    """Every intact record for one capture date. A tampered or foreign line is a refusal.

    Dated by CAPTURE date, so a file named for a day holds what was written that day and a
    reader never has to guess whether a record was back-dated. A store that does not exist holds
    nothing: reading must not create it, and only a write creates it.
    """
    sp = _sp()
    root = Path(store_dir)
    rel = _day_rel(captured_at)  # validated first: an argument is wrong whether or not the
    if not root.is_dir():        # store happens to exist yet, and a reader creates nothing
        return []
    raw = sp.confined_read_bytes(root, rel, what="training snapshots", missing_ok=True)
    if not raw:
        return []
    out = []
    for number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = _contract().loads(line)
        if not isinstance(record, dict) or record.get("v") != SNAPSHOT_VERSION:
            raise _refuse("unknown-value",
                          f"line {number} of {rel} is stamped "
                          f"{(record or {}).get('v')!r}; this reader reads {SNAPSHOT_VERSION!r}")
        out.append(assert_intact(record, f"line {number} of {rel}"))
    return out


def persist(record, store_dir):
    """Append one snapshot -> `{"written", "path", "example_id", "reason"}`.

    IDEMPOTENT BY CONSTRUCTION. `example_id` is derived from `input_sha`, so the same evidence
    captured twice is the same example and the second call writes nothing.

    THE TWO REFUSALS, AND WHICH ONE ACTUALLY BITES. A line edited after it was written fails
    `assert_intact` while it is being read, because the id it carries no longer derives from
    the input it carries -- that is the guard a tampered store meets. The `duplicate-entry`
    below is the OTHER case: two genuinely different inputs whose digests share the leading 16
    hex characters. Through sha256 that needs a 64-bit collision and will not be seen; it is
    refused anyway rather than appended beside, because a store with one id naming two inputs
    is a store no exporter can read. `tests/test_training_data.py` reaches it by crippling the
    digest on purpose, so it is not a branch nothing can test.

    REFUSES WHOLE. A tampered or foreign line anywhere in the day's file fails the read, so
    nothing more is appended to a file whose contents cannot be trusted.
    """
    assert_intact(record, "the record being persisted")
    if record["eligibility"]["status"] != ELIGIBLE_TO_PERSIST:
        raise _refuse("value-invalid",
                      f"the record's eligibility is {record['eligibility']['status']!r}; only "
                      f"{ELIGIBLE_TO_PERSIST!r} may be persisted as training content")
    sp = _sp()
    root = Path(store_dir)
    rel = _day_rel(record["captured_at"])
    for existing in read_snapshots(root, record["captured_at"]):
        if existing["example_id"] != record["example_id"]:
            continue
        if existing["input_sha"] == record["input_sha"]:
            return {"written": False, "path": str(root / rel),
                    "example_id": record["example_id"], "reason": "already-captured"}
        raise _refuse(
            "duplicate-entry",
            f"{record['example_id']} is already stored against a different input digest: two "
            f"different inputs whose digests share a leading prefix. One id naming two inputs "
            f"is a store no exporter can read, so it is refused rather than appended beside")
    data = (canonical(record) + "\n").encode("utf-8")
    if len(data) > MAX_RECORD_BYTES:
        raise _refuse("bounds-exceeded", f"refusing a {len(data)}-byte snapshot line")
    _rt().ensure_private(root)
    sp.confined_append_bytes(root, rel, data, what="training snapshot")
    return {"written": True, "path": str(root / rel), "example_id": record["example_id"],
            "reason": None}


# ==================================================================================================
#  D32 -- THE LABEL LIFECYCLE: REVIEW, CORRECTION, ELIGIBILITY, RETENTION, REVOCATION
# ==================================================================================================
#
# THREE THINGS THAT LOOK LIKE A LABEL, IN THREE DIFFERENT SLOTS, AND CONFLATING ANY TWO IS THE
# DEFECT. `operational_observation` is what the system OBSERVED -- `attempt_ledger`'s own class,
# read off the snapshot and never off the caller. `provider_suggestion` is what a model or a
# service GUESSED -- carried verbatim, flagged, and unable to support anything. `cause` and
# `contributing` are the ADJUDICATED target, and they are filled only when review evidence
# supports them. A claim nobody can support does not land in `cause`: it stays under `claim`, the
# status stays `unresolved`, and `unresolved_reason` names which support was missing.
# `assert_no_adjudicated_field` is the structural half -- a caller's claim may not use the
# adjudicated field names at all, so a suggestion can never arrive already wearing the target's
# clothes.
#
# A REVIEW IS INFORMATION FROM AFTER THE DECISION, AND THE MIRROR OF D31's RULE ENFORCES IT. An
# input entry is refused unless it places `at-or-before-prediction`; an adjudication and an action
# record are refused when they place THERE. A review dated at or before the decision it reviews
# would be a fact the decision could have been shown. D14's defect -- a field populated from what
# merely followed, presented as what the decision produced -- is the same confusion from the other
# side, so `attach_action` carries no field for a cause and none for an optimal action, and it
# reuses `decision_eval.assert_no_causal_claim` rather than standing a second sweep beside it.
#
# WHAT REVOCATION REACHES, AND WHAT IT DOES NOT. Revoking a label refuses every future export,
# invalidates the manifests and datasets built from it, and NAMES the downstream artifacts --
# including a checkpoint. It cannot un-train a model. `REVOCATION_REACH` says which of those two a
# downstream kind gets (`invalidated` or `identified-only`), `REVOCATION_UNREACHED` is carried on
# every revocation record unconditionally, and no branch here can discharge one of those codes by
# passing some other check. The precedent is `workflow_eval.APPROVAL_UNPROVEN`: machine-readable
# codes rather than a paragraph, so a reader can check that no record ever claims more.
#
# WHAT THIS SECTION DOES NOT DO. It is not an exporter: `export_eligibility` DECIDES and writes
# nothing, and the local JSONL dataset and its manifest are D33's, in the section below -- which is
# the CALLER that acts on this decision, and therefore the thing that prevents rather than reports.
# `enforcement-not-provided` stays on every decision here regardless, because a process that reads
# the store without asking is not stopped by an answer. It is not a trainer, and it does
# not turn collection on -- `COLLECTION_ENABLED` and `CAPTURE_WIRED` are still False and nothing
# here reads either as anything else. It is not a second label vocabulary for the decision join:
# `decision_eval.LABEL_STATUSES` describes a joined row's label and is left alone, because a
# training example's adjudication lifecycle and a join's label status answer different questions
# and mapping one onto the other would invent an equivalence neither module can support.

#: The label lifecycle's own schema. ONE constant for the three artifacts below, the way
#: `attempt_ledger.LEDGER_VERSION` stamps every event kind it writes: an adjudication, an action
#: record and a revocation share one envelope (`example_id`, `input_sha`, `kind`, `recorded_at`,
#: `content_sha`) and are revised together, and `kind` is the discriminator, so a reader that
#: fetched one still knows which field names apply to IT. Registered in
#: `release_gate.VERSION_SOURCES` in its own right, because it is a new STORED object.
LIFECYCLE_VERSION = "polytropos.training-label-lifecycle/1"

#: The three artifacts this section writes. Closed: a reader branches on this, and a fourth kind
#: would need its own directory, its own builder and its own refusals.
LIFECYCLE_KINDS = ("adjudication", "action", "revocation")

#: Where each kind lands inside the store, one file per EXAMPLE rather than per day. Keyed by
#: `example_id` on purpose: a revocation has to be findable BEFORE an export, and a gate that
#: could only find one by scanning every day in the store would in practice not look.
LIFECYCLE_DIRS = {
    "adjudication": "labels",
    "action": "actions",
    "revocation": "revocations",
}

#: How many lifecycle records one example may accumulate. Corrections append rather than
#: overwrite, so this bounds a HISTORY, and past it the append is refused rather than the oldest
#: entry dropped -- losing correction history is exactly what must not happen.
MAX_LIFECYCLE_ENTRIES = 32

#: How many references may support one cause, and how many contributing causes one adjudication
#: may name. A review cites what it looked at; a list that could hold hundreds is a bibliography.
MAX_EVIDENCE = 8
MAX_CONTRIBUTING = 8

#: How many downstream artifacts one revocation may name.
MAX_DEPENDENTS = 16

#: What an adjudication's status can be in THIS module's lifecycle.
#:
#:   unadjudicated  a claim was recorded and nobody has reviewed it -- D31's `attach_label`
#:                  status, and the state of an example with no adjudication at all.
#:   unresolved     somebody reviewed it and the evidence does not support a target. NOT the same
#:                  as `unadjudicated`: "nobody looked" and "somebody looked and could not tell"
#:                  are different amounts of information, the distinction
#:                  `workflow_eval.PROMOTION_APPROVAL_BLOCKERS` draws between a missing approval
#:                  and one nobody re-derived.
#:   resolved       review evidence supports the target this record names.
#:   disputed       two adjudications, neither superseding the other, name different targets. It
#:                  is the label, not a failure to label.
LABEL_STATUSES = ("unadjudicated", "unresolved", "resolved", "disputed")

#: The status of an example nobody has adjudicated.
UNADJUDICATED = "unadjudicated"

#: The only status that is a supervised target on its own. `disputed` becomes one only under a
#: question that explicitly models ambiguity, and `unresolved` never does.
SUPERVISED_TARGET_STATUS = "resolved"

#: Which status may follow which -> an EXACT PARTITION of `LABEL_STATUSES` (every status is a key;
#: every value is a member). A correction that keeps the status and changes the target is also
#: admitted -- `resolved` with cause A becoming `resolved` with cause B is the commonest real
#: correction -- and `_assert_label_transition` states that rule where it applies it.
LABEL_STATUS_TRANSITIONS = {
    "unadjudicated": ("unresolved", "resolved", "disputed"),
    "unresolved": ("resolved", "disputed"),
    "resolved": ("unresolved", "disputed"),
    "disputed": ("unresolved", "resolved"),
}

#: The question an adjudication answers. Each shape has its OWN schema below, because the four
#: cases `TRAINING-DATA.md` names do not fit one:
#:
#:   failure-cause  one adjudicated cause from `CAUSE_CLASSES`. `multiple-causes` is a member of
#:                  that taxonomy and needs at least two separately supported contributing
#:                  causes: review established that both contributed.
#:   ambiguity      review could not tell WHICH of several causes it was. No single `cause`, at
#:                  least two competing ones each with its own evidence, and the only shape under
#:                  which a `disputed` history is a supervised target.
#:   no-failure     a successful attempt, which `TRAINING-DATA.md` admits as a negative example
#:                  "only under a compatible explicitly defined question". No cause may be named,
#:                  and the record's operational class must be ABSENT -- a dispatch the ledger
#:                  classified as failing cannot be relabelled a success.
QUESTION_SHAPES = ("failure-cause", "no-failure", "ambiguity")

#: Why an adjudication is `unresolved`, or why a status is not a target. Closed, and deliberately
#: several codes rather than one: WHICH support was missing is the whole information.
#:
#: `insufficient-evidence` is DELIBERATELY not reused here. That string belongs to
#: `decision_eval.METRIC_STATUSES` and means a metric had too few scoreable rows to report a
#: number. A label with no independent reader is not a thin sample, and a review nobody has done
#: is neither; borrowing the word would make three different situations read the same.
UNSUPPORTED_REASONS = ("not-yet-reviewed", "no-supporting-evidence", "no-independent-reader",
                       "provider-suggestion-only", "operational-signal-only",
                       "contributing-causes-not-separately-supported",
                       "disagreement-unresolved")

#: How much one piece of evidence can carry.
#:
#:   review        an independent reader -- a person, or a recorded review verdict. The only
#:                 weight that can establish a `REVIEW_ONLY_CLASSES` member, because "missing
#:                 context" and "implementation error" are judgements and not readings.
#:   mechanical    a reproduction or a tool failure stage. It narrows a cause and can support a
#:                 deterministic one; it is an observation rather than a judgement.
#:   operational   the ledger's own classification of the dispatch. This is the CANDIDATE route
#:                 D31 built, and it supports NOTHING here: a nonzero exit is the symptom
#:                 `TRAINING-DATA.md` says to keep distinct from a cause.
EVIDENCE_WEIGHTS = ("review", "mechanical", "operational")

#: How each `decision_eval.LABEL_SOURCES` member weighs as review evidence -> the whole
#: reconciliation, checked by `reconcile_label_sources` as an EXACT PARTITION of that tuple read
#: at call time. That module owns who produced an observation; this one owns what such an
#: observation can support. A source it adds and this has no weight for would otherwise arrive
#: weightless and quietly support a target.
EVIDENCE_ADMISSIBILITY = {
    "human-adjudication": "review",
    "review-verdict": "review",
    "tests-oracle": "mechanical",
    "kit-acceptance": "mechanical",
    "attempt-outcome": "operational",
}

#: What a later action's outcome can be, exactly as `TRAINING-DATA.md` names it.
ACTION_OUTCOMES = ("success", "failure", "unknown")

#: How an attempt result reads as an action outcome -> checked by `reconcile_action_outcomes`
#: against `decision_eval`'s three result vocabularies read at call time, in BOTH directions: the
#: map must name every result, and every recovered result must read as `success`, every failed one
#: as `failure`, and every CENSORED one as `unknown`. That last rule is the one worth having -- a
#: censored result is an outcome nobody has yet, and reading it as a failure would manufacture a
#: negative example out of an attempt that is merely still open.
RESULT_TO_ACTION_OUTCOME = {
    "pass": "success",
    "retry-pass": "success",
    "escalated-pass": "success",
    "verify-failed": "failure",
    "dispatch-failed": "failure",
    "blocked": "failure",
    "open": "unknown",
    "unknown": "unknown",
    "dispatched": "unknown",
    "budget-stop": "unknown",
}

#: Which eligibility state may follow which -> an EXACT PARTITION of `ELIGIBILITY_STATUSES`. Two
#: properties are the point. `approved` appears in exactly one row, `unknown`'s: an expired record
#: is never silently renewed and a revoked one is never reinstated. `revoked` is reachable from
#: every state and leads nowhere, so a withdrawal cannot be undone to make an export valid again.
#: (`approved` -> `unknown` is the degradation `eligibility_state` applies when a retention period
#: cannot be computed at all: an approval nobody can enforce is not an approval.)
ELIGIBILITY_TRANSITIONS = {
    "unknown": ("approved", "refused", "revoked"),
    "approved": ("unknown", "expired", "revoked"),
    "refused": ("revoked",),
    "expired": ("revoked",),
    "revoked": (),
}

#: The states nothing leads out of.
ELIGIBILITY_TERMINAL = ("revoked",)

#: What can be built out of a training example, and therefore what a revocation has to say
#: something about. Closed: a kind nobody mapped in `REVOCATION_REACH` is refused rather than
#: silently reported as invalidated.
DOWNSTREAM_KINDS = ("export-manifest", "derived-dataset", "readiness-report",
                    "trained-checkpoint")

#: How far revocation reaches into one downstream artifact.
#:
#:   invalidated       this store will not honour it again: a manifest, a dataset or a report
#:                     built from a revoked example is marked invalid and no re-export reproduces
#:                     it.
#:   identified-only   it is NAMED, and nothing more.
REACH_LEVELS = ("invalidated", "identified-only")

#: Which reach each downstream kind gets -> an EXACT PARTITION of `DOWNSTREAM_KINDS`. The
#: `trained-checkpoint` row is the most consequential line in this module: a checkpoint trained on
#: a revoked example is IDENTIFIED and never unlearned. Deleting the example does not remove it
#: from weights, and nothing here may read as though it did.
REVOCATION_REACH = {
    "export-manifest": "invalidated",
    "derived-dataset": "invalidated",
    "readiness-report": "invalidated",
    "trained-checkpoint": "identified-only",
}

#: What revoking DOES establish, as codes rather than prose.
REVOCATION_REACHES = ("future-exports-refused", "dependent-manifests-invalidated",
                      "downstream-artifacts-identified")

#: What revoking does NOT establish, whatever else was checked and however many dependents were
#: named. UNCONDITIONAL, closed, and carried on every revocation record: nothing in this section
#: can discharge one of these, so none is ever left off on the strength of some other check.
REVOCATION_UNREACHED = ("trained-weights-not-unlearned", "exported-copies-not-recalled",
                        "downstream-artifacts-not-rebuilt", "byte-erasure-not-proven")

REVOCATION_UNREACHED_NOTES = {
    "trained-weights-not-unlearned":
        "a model already trained on this example does not forget it because the example was "
        "withdrawn. Revocation NAMES the checkpoint; removing one example's influence from "
        "trained weights is a training-side problem this module neither performs nor claims",
    "exported-copies-not-recalled":
        "bytes that already left this store are outside its reach. A revocation refuses the NEXT "
        "export and invalidates the manifests it was shown; it does not travel to a copy "
        "somebody already holds",
    "downstream-artifacts-not-rebuilt":
        "marking a manifest or a dataset invalid is a statement about it, not an action on it. "
        "Nothing here rebuilds, retracts or deletes a downstream artifact -- D33 owns exports, "
        "and what this module owns is the refusal that stops the next one",
    "byte-erasure-not-proven":
        "the tombstone records that the withdrawal happened. It does not prove the example's "
        "bytes are gone: this tree is distributed, cached and often backed up, and a file "
        "deletion is not an erasure proof",
}

UNLEARNING_NOTE = (
    "revocation refuses future exports, invalidates the dependent manifests named on the record, "
    "and IDENTIFIES the downstream artifacts built from this example. It does not un-train a "
    "model: a checkpoint is named, never unlearned, and every code in `unreached` stays on the "
    "record whatever else was checked")

#: What no adjudication written here establishes. Unconditional, on every adjudication, for the
#: reason `APPROVAL_UNPROVEN` is unconditional.
ADJUDICATION_NOT_ESTABLISHED = ("reviewer-not-authenticated", "evidence-not-dereferenced",
                                "cause-not-experimentally-confirmed")

ADJUDICATION_NOT_ESTABLISHED_NOTES = {
    "reviewer-not-authenticated":
        "the reviewer is a name and a source this function was handed. There is no controller "
        "identity, no signature and no session behind either, so an adjudication binds WHAT was "
        "reviewed exactly and WHO reviewed it not at all",
    "evidence-not-dereferenced":
        "the evidence references are pointers. This function checks that each one IS a reference "
        "and names the parts it is missing; it reads nothing at the other end, so it cannot say "
        "the object exists or still says what it said",
    "cause-not-experimentally-confirmed":
        "review is reading, not intervention. A cause established by an independent reader is not "
        "a cause established by changing one thing and watching the failure go away, and a "
        "recovery that succeeded is not evidence the diagnosis behind it was right",
}

#: Every refusal an export decision may carry. Closed, and each one separately reachable --
#: `tests/test_training_data.py` constructs a case for every member, because a code nothing can
#: emit reads as a guard and is not one.
EXPORT_REFUSALS = ("record-not-intact", "retention-unknown", "eligibility-unknown",
                   "eligibility-refused", "eligibility-expired", "eligibility-revoked",
                   "label-not-checked", "label-unadjudicated", "label-unresolved",
                   "label-disputed", "revocation-not-checked", "purpose-not-declared",
                   "purpose-outside-scope", "destination-not-declared")

#: What an export DECISION does not establish, carried unconditionally on every one.
EXPORT_NOT_ESTABLISHED = ("destination-not-contacted", "enforcement-not-provided",
                          "purpose-strings-compared-not-interpreted")

EXPORT_NOT_ESTABLISHED_NOTES = {
    "destination-not-contacted":
        "a destination is a string this decision was handed. Nothing here starts a connection, "
        "authenticates to anything or transfers a byte, and no external transfer is part of V1",
    "enforcement-not-provided":
        "this function decides; it does not prevent. A process that ignores the decision and "
        "reads the store directly is stopped by the store's own permissions and by the execution "
        "boundary, which are other modules' business",
    "purpose-strings-compared-not-interpreted":
        "the declared export purpose is compared with the scope's permitted purpose as TEXT. Two "
        "different wordings of the same purpose refuse, and a purpose that matches the words "
        "while meaning something else passes -- a string comparison cannot read intent",
}

LABEL_VOCABULARY_NOTE = (
    "this lifecycle's statuses are not decision_eval.LABEL_STATUSES. That vocabulary describes a "
    "joined row's label; this one describes whether a training target has been adjudicated. "
    "`unresolved` here means somebody reviewed it and could not tell, which is neither a missing "
    "label nor a censored observation, so the two vocabularies are kept apart rather than mapped")


# ---- the reconciliations D32 adds, each read from its owner at call time -------------------------

def reconcile_label_sources():
    """How `decision_eval.LABEL_SOURCES` weighs as review evidence -> the reconciliation.

    An EXACT PARTITION of that tuple, read at call time and refused in both directions for the
    reason `reconcile_operational_classes` gives: a source the owner adds and this module has no
    weight for would arrive weightless, and a weight for a source the owner removed is a
    vocabulary nobody writes.

    THE LAST CHECK IS THE INTERESTING ONE. `decision_eval.HUMAN_LABEL_SOURCES` names which
    sources are a person, and that module's rule is that a human verdict is not ground truth. A
    human source that did not weigh as `review` would be a person's judgement counted as a
    mechanical reading, so it refuses here.
    """
    de = _de()
    owner = tuple(de.LABEL_SOURCES)
    mapped = set(EVIDENCE_ADMISSIBILITY)
    missing = sorted(set(owner) - mapped)
    extra = sorted(mapped - set(owner))
    if missing or extra:
        raise _refuse(
            "unknown-value",
            f"the evidence reconciliation is no longer an exact partition of "
            f"decision_eval.LABEL_SOURCES: unweighed {missing or 'none'}, unknown "
            f"{extra or 'none'}. That module owns who produced an observation; this one owns "
            f"what such an observation can support, and a silent gap would mean evidence "
            f"weighing nothing while supporting a target")
    bad = sorted(v for v in EVIDENCE_ADMISSIBILITY.values() if v not in EVIDENCE_WEIGHTS)
    if bad:
        raise _refuse("unknown-value",
                      f"the evidence reconciliation weighs a source as {bad}, which are not "
                      f"members of EVIDENCE_WEIGHTS")
    human = tuple(de.HUMAN_LABEL_SOURCES)
    stray = sorted(set(human) - set(owner))
    if stray:
        raise _refuse("unknown-value",
                      f"decision_eval.HUMAN_LABEL_SOURCES names {stray}, which is not one of its "
                      f"own LABEL_SOURCES")
    misweighed = sorted(name for name in human if EVIDENCE_ADMISSIBILITY[name] != "review")
    if misweighed:
        raise _refuse(
            "unknown-value",
            f"{misweighed} is a human source weighed as something other than review. A person's "
            f"judgement is an independent reader, never a mechanical reading")
    return {
        "lifecycle_v": LIFECYCLE_VERSION,
        "owner": "bin/decision_eval.py:LABEL_SOURCES",
        "sources": list(owner),
        "weights": list(EVIDENCE_WEIGHTS),
        "weight_of": dict(sorted(EVIDENCE_ADMISSIBILITY.items())),
        "human_sources": list(human),
        "review_only_classes": list(REVIEW_ONLY_CLASSES),
        "note": CANDIDATE_LABEL_NOTE,
    }


def reconcile_action_outcomes():
    """How an attempt result reads as an action outcome -> the reconciliation.

    Checked three ways against `decision_eval`, read at call time: its three result vocabularies
    must stay disjoint, the map must be an exact partition of their union, and each group must map
    onto the outcome its own meaning implies. The third check is what stops a censored result --
    an attempt still open, a budget stop, a dispatch nobody graded -- from reading as a failure
    and becoming a negative training example.
    """
    de = _de()
    recovered = tuple(de.RECOVERED_RESULTS)
    failed = tuple(de.FAILED_RESULTS)
    censored = tuple(de.CENSORING_BY_RESULT)
    owner = recovered + failed + censored
    dupes = sorted({name for name in owner if owner.count(name) > 1})
    if dupes:
        raise _refuse(
            "duplicate-entry",
            f"decision_eval now lists {dupes} in more than one of RECOVERED_RESULTS, "
            f"FAILED_RESULTS and CENSORING_BY_RESULT. One result, one meaning: reconcile them "
            f"there before this module reads them as an outcome")
    mapped = set(RESULT_TO_ACTION_OUTCOME)
    missing = sorted(set(owner) - mapped)
    extra = sorted(mapped - set(owner))
    if missing or extra:
        raise _refuse(
            "unknown-value",
            f"the action-outcome reconciliation is no longer an exact partition of "
            f"decision_eval's result vocabularies: unmapped {missing or 'none'}, unknown "
            f"{extra or 'none'}")
    for group, expected in ((recovered, "success"), (failed, "failure"), (censored, "unknown")):
        wrong = sorted(name for name in group if RESULT_TO_ACTION_OUTCOME[name] != expected)
        if wrong:
            raise _refuse(
                "unknown-value",
                f"{wrong} should read as {expected!r} and does not. A recovered result is a "
                f"success, a failed one is a failure, and a CENSORED one is unknown -- an "
                f"outcome nobody has yet is not a negative example")
    bad = sorted(v for v in RESULT_TO_ACTION_OUTCOME.values() if v not in ACTION_OUTCOMES)
    if bad:
        raise _refuse("unknown-value",
                      f"the action-outcome reconciliation maps onto {bad}, which are not members "
                      f"of ACTION_OUTCOMES")
    return {
        "lifecycle_v": LIFECYCLE_VERSION,
        "owner": "bin/decision_eval.py:RECOVERED_RESULTS+FAILED_RESULTS+CENSORING_BY_RESULT",
        "outcomes": list(ACTION_OUTCOMES),
        "outcome_of": dict(sorted(RESULT_TO_ACTION_OUTCOME.items())),
        "censored_results": sorted(censored),
        "note": de.UNTRIED_ACTION_NOTE,
    }


def action_outcome(result):
    """One attempt result -> its action outcome, or None when no result was recorded.

    `None` in means nothing was graded, and `None` out says so. Nothing here invents a failure for
    an action nobody graded.
    """
    reconcile_action_outcomes()
    if result is None:
        return None
    if result not in RESULT_TO_ACTION_OUTCOME:
        raise _refuse("unknown-value",
                      f"{result!r} is not one of decision_eval's attempt results")
    return RESULT_TO_ACTION_OUTCOME[result]


def _assert_partition(mapping, owner_names, values, what, owner_label):
    """One closed mapping, checked against the tuple that owns its keys -> the mapping."""
    missing = sorted(set(owner_names) - set(mapping))
    extra = sorted(set(mapping) - set(owner_names))
    if missing or extra:
        raise _refuse("unknown-value",
                      f"{what} is not an exact partition of {owner_label}: unmapped "
                      f"{missing or 'none'}, unknown {extra or 'none'}")
    flat = []
    for value in mapping.values():
        flat.extend(value if isinstance(value, (list, tuple)) else [value])
    bad = sorted(set(flat) - set(values))
    if bad:
        raise _refuse("unknown-value", f"{what} names {bad}, which are not admissible values")
    return mapping


# ---- refusing a claim that arrives already wearing the target's clothes --------------------------

#: Key spellings that belong to an ADJUDICATED slot. A caller's claim, and a provider's
#: suggestion, may not use one: `claim: {"cause": "missing-context"}` would be a guess written
#: into the field review is supposed to fill, which is the three-way separation collapsing at the
#: point of entry. `claimed_cause` is the spelling that works, and it is the one D31's own demo
#: already used.
_ADJUDICATED_SHAPED = frozenset(
    _alnum(name) for name in ("cause", "causes", "contributing", "status", "adjudicated",
                              "adjudication", "operational_observation", "candidate_cause",
                              "supervised_target", "target", "evidence", "reviewer", "unreached",
                              "not_established", "shape")
)


def _walk_keys(value):
    """Every key in a JSON-shaped structure, plus the types the walk could not descend into.

    ONE walker for the three key sweeps in this module, so "what counts as inspected" has one
    answer. A container the walk does not enter inspects nothing and certifies everything, so
    bytes, a set, a view, a generator and any other object come back as unwalkable rather than
    silently passing. A namedtuple is unwalkable although it IS a tuple, because walking it as one
    would inspect its values and never its field names -- which is where a banned key would hide.
    """
    keys = []
    unwalkable = []
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, Mapping):
            for key, sub in item.items():
                keys.append(key)
                stack.append(sub)
        elif isinstance(item, (str, int, float, type(None))):
            continue  # the JSON scalars; `bool` is an `int` and arrives here
        elif hasattr(item, "_fields"):
            unwalkable.append(type(item).__name__)  # a namedtuple: values walked, names lost
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
        else:
            unwalkable.append(type(item).__name__)
    return keys, unwalkable


def _refuse_keys(hits, unwalkable, where, why):
    """The one refusal both key sweeps raise, so a caller branches on one code."""
    if hits:
        raise _refuse("authority-field",
                      f"{where} carries {', '.join(repr(h) for h in sorted(set(hits)))}, {why}")
    if unwalkable:
        raise _refuse(
            "authority-field",
            f"{where} carries a value this sweep cannot inspect: "
            f"{', '.join(sorted(set(unwalkable)))}. A container that is not walked is not "
            f"checked, so it is refused rather than passed over")


def assert_no_adjudicated_field(value, where="the claim"):
    """Refuse a claim or a suggestion that uses an adjudicated field name at any depth.

    WHAT IT DOES NOT PROVE. It matches KEY spellings, so a suggestion that writes a cause into a
    VALUE under an innocent key passes. What stops that one is not a spelling list: `cause` on the
    record is written by `adjudicate` from the SUPPORTED target and from nowhere else, so whatever
    a claim says, the adjudicated slot still holds only what review established.
    """
    keys, unwalkable = _walk_keys(value)
    hits = [key for key in keys
            if isinstance(key, str) and (_alnum(key) in _ADJUDICATED_SHAPED
                                         or any(_alnum(part) in _ADJUDICATED_SHAPED
                                                for part in key.split(".")))]
    _refuse_keys(hits, unwalkable, where,
                 "which is an adjudicated field name. A raw observation and a provider's "
                 "suggestion are recorded as claims; only review evidence fills the target")
    return value


#: Words that would claim a model forgot something. Matched as WHOLE WORDS after a key is split on
#: punctuation and on camelCase humps, which is stricter than the dotted-segment match
#: `assert_no_input_field` uses. `decision_eval.CAUSAL_TOKENS` has to list `cause` beside
#: `rootcause` precisely because a whole-key match on `cause` would fire on the innocent
#: `root_cause`; these words have no innocent compound in this record's vocabulary, so splitting
#: into words catches `weights_purged` and `scrubbedFromWeights` without that hazard.
UNLEARNING_WORDS = ("unlearn", "unlearned", "unlearning", "untrain", "untrained", "forget",
                    "forgot", "forgotten", "scrub", "scrubbed", "purge", "purged", "erase",
                    "erased", "expunge", "expunged", "amnesia")

_UNLEARNING_WORDS = frozenset(UNLEARNING_WORDS)


def _key_words(key):
    if not isinstance(key, str):
        return ()
    humped = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", key)
    return tuple(word for word in re.split(r"[^A-Za-z0-9]+", humped.lower()) if word)


def assert_no_unlearning_claim(value, where="the revocation"):
    """Refuse a structure whose keys would claim a model unlearned something.

    THE ROUTE IS REAL. `revoke`'s dependents are the caller's own object with the caller's own
    keys, and "we withdrew it, so the model no longer knows it" is the single most tempting false
    claim in this file. A field called `unlearned`, `weights_purged` or `scrubbedFromWeights`
    asserts exactly that, so it is refused rather than stored beside `REVOCATION_UNREACHED`
    contradicting it.

    WHAT IT DOES NOT PROVE. A spelling list is not a decision procedure. A key this list never
    anticipated -- `weights_clean`, `no_longer_influences` -- is not caught, and a VALUE making
    the claim is not caught either; widening the list can only move that line. What carries the
    honest claim is structural: every revocation record carries every `REVOCATION_UNREACHED` code
    unconditionally, and no branch here can take one off.
    """
    keys, unwalkable = _walk_keys(value)
    hits = [key for key in keys if any(word in _UNLEARNING_WORDS for word in _key_words(key))]
    _refuse_keys(hits, unwalkable, where,
                 "which would claim a model forgot this example. Revocation refuses future "
                 f"exports and names downstream artifacts; it un-trains nothing. {UNLEARNING_NOTE}")
    return value


# ---- the lifecycle envelope ---------------------------------------------------------------------

def _example_id(value):
    """An example id, checked as an identity AND as a single filename component."""
    text = _label_text(value, "an example id", limit=64)
    if not re.fullmatch(r"ex-[0-9a-f]{16}", text):
        raise _refuse("value-invalid",
                      f"an example id is 'ex-' and 16 hex characters derived from the input "
                      f"digest, got {text!r}")
    return _sp().validate_id(text, "an example id")


def _example_rel(kind, example_id):
    if kind not in LIFECYCLE_DIRS:
        raise _refuse("unknown-value", f"{kind!r} is not one of {', '.join(LIFECYCLE_KINDS)}")
    return f"{LIFECYCLE_DIRS[kind]}/{_example_id(example_id)}.jsonl"


def _assert_labelable(record, what):
    """A lifecycle artifact that IS training content is built only for an approved record.

    Revocation is the one exempt path, and has to be: a record must be withdrawable precisely
    when it is no longer approved.
    """
    status = record.get("eligibility", {}).get("status") if isinstance(record, Mapping) else None
    if status != ELIGIBLE_TO_PERSIST:
        raise _refuse(
            "value-invalid",
            f"the record's eligibility is {status!r}; only {ELIGIBLE_TO_PERSIST!r} records get "
            f"{what}. Withdrawing one is always available; adding training content to one is not")
    return record


def _envelope(record, kind, *, recorded_at):
    """The fields every lifecycle artifact carries, taken from the snapshot it points at."""
    assert_intact(record, f"the record being given a {kind}")
    return {
        "v": LIFECYCLE_VERSION,
        "kind": _one_of(kind, LIFECYCLE_KINDS, "the lifecycle kind"),
        "example_id": _example_id(record["example_id"]),
        "input_sha": _digest_or_none(record["input_sha"], "the record's input_sha"),
        "taxonomy_v": TAXONOMY_VERSION,
        "recorded_at": recorded_at,
    }


def _seal(entry):
    """The content digest every lifecycle record carries -> the record, sealed and bounded."""
    entry["content_sha"] = _sha({k: v for k, v in entry.items() if k != "content_sha"})
    size = len(canonical(entry).encode("utf-8"))
    if size > MAX_RECORD_BYTES:
        raise _refuse("bounds-exceeded",
                      f"the {entry['kind']} serializes to {size} bytes, past the "
                      f"{MAX_RECORD_BYTES} one lifecycle record holds")
    return entry


def lifecycle_integrity(entry):
    """Recompute a lifecycle record's digest -> `{"content_sha_ok", "recomputed"}`."""
    if not isinstance(entry, Mapping) or entry.get("v") != LIFECYCLE_VERSION:
        raise _refuse("not-a-reference", f"this is not a {LIFECYCLE_VERSION} record")
    if entry.get("kind") not in LIFECYCLE_KINDS:
        raise _refuse("unknown-value",
                      f"a lifecycle record's kind is one of {', '.join(LIFECYCLE_KINDS)}, got "
                      f"{entry.get('kind')!r}")
    recomputed = _sha({k: v for k, v in entry.items() if k != "content_sha"})
    return {"content_sha_ok": recomputed == entry.get("content_sha"), "recomputed": recomputed}


def assert_lifecycle_intact(entry, where="the stored lifecycle record"):
    if not lifecycle_integrity(entry)["content_sha_ok"]:
        raise _refuse("value-invalid",
                      f"{where} fails content_sha_ok: its bytes are not the bytes that were "
                      f"digested, so it is not the record it claims to be")
    return entry


def _after_the_decision(instant, record, what):
    """The mirror of D31's input rule: this fact must NOT place at or before the decision.

    `_instant` has already refused anything unplaceable, so the only two answers left are the two
    this branch tells apart, and the admissible-for-an-input one is the refusal here.
    """
    where = _de().placement(instant, record["prediction_at"])
    if where == ADMISSIBLE_PLACEMENT:
        raise _refuse(
            "value-invalid",
            f"{what} is dated {instant} and the decision was taken {record['prediction_at']}, so "
            f"it places {where!r}. A later artifact must place after the decision: anything at or "
            f"before it is evidence the decision could have been shown, and this record is not an "
            f"input")
    return where


# ---- review evidence ----------------------------------------------------------------------------

def review_evidence(*, source, ref, observed_at, stage=None):
    """One piece of review evidence -> its payload, weighed by its source.

    `stage` is `TRAINING-DATA.md`'s "tool failure stage": where in the run the tool gave up. Free
    text, bounded, optional, because a reviewer honestly may not know it.

    The placement recorded here is deliberate. Review evidence is normally information from AFTER
    the decision, and saying so ON the evidence is how a reader knows it may never be moved into
    an input. Nothing is refused for placing later -- that is what review IS.
    """
    weights = reconcile_label_sources()["weight_of"]
    src = _one_of(source, tuple(sorted(weights)), "the evidence's source")
    pointer = _al().read_ref(ref)
    if pointer is None:
        raise _refuse("not-a-reference",
                      f"the evidence's ref must come from attempt_ledger.make_ref, got {ref!r}")
    return {
        "source": src,
        "weight": weights[src],
        "ref": dict(pointer),
        "ref_gaps": _al().ref_gaps(pointer),
        "observed_at": _instant(observed_at, "the evidence's observed_at"),
        "stage": _label_text(stage, "the evidence's stage", optional=True),
    }


_EVIDENCE_KEYS = ("source", "weight", "ref", "ref_gaps", "observed_at", "stage")


def _evidence_list(items, where):
    """A caller's evidence sequence, re-derived through `review_evidence` -> the payloads.

    Re-derived rather than trusted: the `weight` on a stored payload is recomputed from its
    source, so a caller cannot hand over `{"source": "attempt-outcome", "weight": "review"}` and
    have the ledger's own classification counted as an independent reader.
    """
    if isinstance(items, (str, bytes, Mapping)):
        raise _refuse("wrong-type",
                      f"{where} is a sequence of evidence payloads, not {type(items).__name__}")
    built = list(items)
    if len(built) > MAX_EVIDENCE:
        raise _refuse("bounds-exceeded",
                      f"{where} carries {len(built)} references, past the {MAX_EVIDENCE} one "
                      f"adjudicated cause cites")
    out = []
    for index, item in enumerate(built):
        payload = _closed(item, _EVIDENCE_KEYS, f"{where}[{index}]")
        if payload.get("ref") is None or payload.get("source") is None:
            raise _refuse("value-invalid",
                          f"{where}[{index}] did not come from training_data.review_evidence")
        out.append(review_evidence(source=payload["source"], ref=payload["ref"],
                                   observed_at=payload["observed_at"],
                                   stage=payload.get("stage")))
    return out


def _support(items):
    """The weights present in one evidence list -> `{weight: count}`, every weight answered."""
    tally = {weight: 0 for weight in EVIDENCE_WEIGHTS}
    for item in items:
        tally[item["weight"]] += 1
    return tally


def _supports_a_cause(cause, tally):
    """Whether this evidence can establish this cause -> `(bool, reason or None)`.

    Two rules, and WHICH one bit is the information. Any adjudicated cause needs support that is
    not merely operational -- the ledger's classification of a dispatch is the candidate route,
    never the target. A `REVIEW_ONLY_CLASSES` member needs an independent READER on top: those
    three are judgements, and D31 asserted they are unreachable from any operational signal.
    """
    if tally["review"] + tally["mechanical"] == 0:
        return False, ("operational-signal-only" if tally["operational"]
                       else "no-supporting-evidence")
    if cause in REVIEW_ONLY_CLASSES and tally["review"] == 0:
        return False, "no-independent-reader"
    return True, None


# ---- adjudication -------------------------------------------------------------------------------

def _reviewer(value):
    payload = _closed(value, ("id", "source"), "the reviewer")
    weights = reconcile_label_sources()["weight_of"]
    source = _one_of(payload.get("source"), tuple(sorted(weights)), "the reviewer's source")
    if weights[source] != "review":
        raise _refuse("value-invalid",
                      f"a reviewer's source weighs as {weights[source]!r}. An adjudication is "
                      f"made by an independent reader, not by a mechanical signal and not by the "
                      f"ledger's own classification of the dispatch")
    return {"id": _label_text(payload.get("id"), "the reviewer's id"), "source": source}


def _cause(value, where, *, optional=False):
    if value is None:
        if optional:
            return None
        raise _refuse("missing-field", f"{where} is required")
    return _one_of(value, CAUSE_CLASSES, where)


def _contributing(items, where):
    """Each contributing cause with its OWN evidence -> the rows, each separately weighed.

    Evidence is attached per cause rather than pooled, because "two causes contributed" is two
    claims and pooling would let one well-evidenced cause carry a second nobody looked into.
    """
    if isinstance(items, (str, bytes, Mapping)):
        raise _refuse("wrong-type",
                      f"{where} is a sequence of {{cause, evidence}} entries, not "
                      f"{type(items).__name__}")
    built = list(items)
    if len(built) > MAX_CONTRIBUTING:
        raise _refuse("bounds-exceeded",
                      f"{where} names {len(built)} causes, past the {MAX_CONTRIBUTING} one "
                      f"adjudication holds")
    out = []
    seen = set()
    for index, item in enumerate(built):
        payload = _closed(item, ("cause", "evidence"), f"{where}[{index}]")
        cause = _cause(payload.get("cause"), f"{where}[{index}].cause")
        if cause in seen:
            raise _refuse("duplicate-entry",
                          f"{where} names {cause!r} twice; one contributing cause, one entry")
        seen.add(cause)
        items_for = _evidence_list(payload.get("evidence") or (), f"{where}[{index}].evidence")
        tally = _support(items_for)
        supported, reason = _supports_a_cause(cause, tally)
        out.append({"cause": cause, "evidence": items_for, "support": tally,
                    "supported": supported, "unsupported_reason": reason})
    return out


def _suggestion(value):
    """A model's or a service's suggested label -> a CANDIDATE, recorded and never believed."""
    if value is None:
        return None
    payload = _closed(value, ("by", "claim"), "the provider suggestion")
    pointer = _al().read_ref(payload.get("by"))
    if pointer is None:
        raise _refuse("not-a-reference",
                      "the suggestion's `by` must come from attempt_ledger.make_ref: a "
                      "suggestion nobody can attribute cannot be weighed or withdrawn")
    claim = payload.get("claim")
    if not isinstance(claim, Mapping) or not claim:
        raise _refuse("value-invalid", "a provider suggestion carries a non-empty claim object")
    assert_no_input_field(claim, "the provider suggestion")
    assert_no_adjudicated_field(claim, "the provider suggestion")
    return {
        "by": dict(pointer),
        "claim": _copy(dict(claim)),
        "adjudicated": False,
        "note": ("a model's or a service's suggestion is a candidate label, never independently "
                 "verified truth. It supports nothing here: an adjudicated target needs review "
                 "evidence, and a suggestion is not evidence about itself"),
    }


def _assert_label_transition(current, target, *, changed):
    """Refuse a correction that is not a transition, or one that re-derived nothing.

    Same status with a different target is admitted, because `resolved` with cause A becoming
    `resolved` with cause B is the commonest real correction. Same status AND the same target is
    refused: a correction that changed nothing is a second record asserting the first, and
    `workflow_eval` refuses an approval that re-derived nothing for the same reason.
    """
    _one_of(current, LABEL_STATUSES, "the prior status")
    _one_of(target, LABEL_STATUSES, "the corrected status")
    if current == target:
        if not changed:
            raise _refuse(
                "value-invalid",
                f"this correction leaves the status {current!r} and the target unchanged, so it "
                f"re-derived nothing. A correction says what was wrong with the record it "
                f"supersedes; one that asserts the same thing again is a duplicate")
        return target
    if target not in LABEL_STATUS_TRANSITIONS[current]:
        raise _refuse("unknown-value",
                      f"{current!r} does not lead to {target!r}; from {current!r} the transitions "
                      f"are {LABEL_STATUS_TRANSITIONS[current] or 'none'}")
    return target


def _target_key(entry):
    return (entry["shape"], entry["cause"],
            tuple(row["cause"] for row in entry["contributing"]))


def adjudicate(record, *, shape, reviewer, decided_at, claim=None, cause=None, contributing=(),
               evidence=(), suggestion=None, prior=None, correction_reason=None):
    """A reviewed label for one snapshot -> a separate `adjudication` artifact.

    IT CANNOT TOUCH THE SNAPSHOT. What comes back points at `example_id` and `input_sha`; the
    record is not copied into it, not rewritten and not returned. `assert_intact` runs first, so
    an adjudication is never attached to a record whose bytes have moved.

    AN UNSUPPORTED CLAIM STAYS UNRESOLVED. `cause` is an ASK. It is written to the record only
    when the evidence supports it; otherwise the record carries `cause: None`, `status:
    "unresolved"` and the `unresolved_reason` naming which support was missing, and the ask
    survives under `claim` as what somebody proposed. Nothing is defaulted, nothing is guessed,
    and no symptom is promoted to a cause.

    THE THREE ORIGINS STAY APART. `operational_observation` is copied off the snapshot's own
    `candidate_cause`, so the caller cannot supply it. `provider_suggestion` is the caller's and
    weighs nothing. `cause`/`contributing` are the adjudicated target. A claim or a suggestion
    arriving under one of the adjudicated field names is refused outright.
    """
    shape = _one_of(shape, QUESTION_SHAPES, "the question shape")
    _assert_labelable(record, "an adjudicated target")
    decided = _instant(decided_at, "the adjudication's decided_at")
    entry = _envelope(record, "adjudication", recorded_at=decided)
    _after_the_decision(decided, record, "the adjudication")
    who = _reviewer(reviewer)
    if claim is not None:
        if not isinstance(claim, Mapping) or not claim:
            raise _refuse("value-invalid", "a claim is a non-empty object")
        assert_no_input_field(claim, "the adjudication's claim")
        assert_no_adjudicated_field(claim, "the adjudication's claim")
    primary = _cause(cause, "the adjudicated cause", optional=True)
    rows = _contributing(contributing, "the contributing causes")
    direct = _evidence_list(evidence, "the adjudication's evidence")
    tally = _support(direct)
    guess = _suggestion(suggestion)

    status = "resolved"
    reason = None
    if shape == "no-failure":
        if primary is not None or rows:
            raise _refuse(
                "value-invalid",
                "a no-failure example names no cause: TRAINING-DATA.md's rule is that a "
                "successful attempt may be a negative example only under a compatible question, "
                "never forced into the failure-cause taxonomy")
        if record["candidate_cause"]["from_operational"] is not None:
            raise _refuse(
                "value-invalid",
                f"this record's operational class is "
                f"{record['candidate_cause']['from_operational']!r}, so the ledger classified the "
                f"dispatch as failing. A failed dispatch cannot be adjudicated as a no-failure "
                f"example: None is classify_dispatch's own answer for one that did not fail")
        if tally["review"] + tally["mechanical"] == 0:
            status = "unresolved"
            reason = ("operational-signal-only" if tally["operational"]
                      else "no-supporting-evidence")
    elif shape == "ambiguity":
        if primary is not None:
            raise _refuse(
                "value-invalid",
                "an ambiguity adjudication names no single cause -- that the causes cannot be "
                "told apart is the target. Name the competing ones under `contributing`")
        if len(rows) < 2:
            raise _refuse("value-invalid",
                          f"an ambiguity adjudication names at least two competing causes, got "
                          f"{len(rows)}")
        if tally["review"] == 0:
            status, reason = "unresolved", "no-independent-reader"
        elif any(not row["supported"] for row in rows):
            status, reason = "unresolved", "contributing-causes-not-separately-supported"
    else:
        if primary is None:
            raise _refuse("missing-field",
                          "a failure-cause adjudication names the cause it establishes")
        supported, why = _supports_a_cause(primary, tally)
        if not supported:
            status, reason = "unresolved", why
        elif primary == "multiple-causes" and (
                len(rows) < 2 or any(not row["supported"] for row in rows)):
            status, reason = "unresolved", "contributing-causes-not-separately-supported"
    if status == "unresolved" and guess is not None and not direct and not any(
            row["evidence"] for row in rows):
        reason = "provider-suggestion-only"
    _one_of(reason, UNSUPPORTED_REASONS + (None,), "the unresolved reason")

    entry.update({
        "shape": shape,
        "status": _one_of(status, LABEL_STATUSES, "the adjudication's status"),
        "cause": primary if status == "resolved" else None,
        "contributing": rows,
        "claim": _copy(dict(claim)) if claim else None,
        "unresolved_reason": reason,
        "evidence": direct,
        "support": tally,
        "reviewer": who,
        "decided_at": decided,
        "decided_placement": _de().placement(decided, record["prediction_at"]),
        "operational_observation": {
            "class": record["candidate_cause"]["class"],
            "from_operational": record["candidate_cause"]["from_operational"],
            "adjudicated": False,
            "note": CANDIDATE_LABEL_NOTE,
        },
        "provider_suggestion": guess,
        "supersedes": None,
        "correction": None,
        "not_established": list(ADJUDICATION_NOT_ESTABLISHED),
        "not_established_notes": dict(sorted(ADJUDICATION_NOT_ESTABLISHED_NOTES.items())),
        "notes": [LABEL_SEPARATE_NOTE, LABEL_VOCABULARY_NOTE, REDACTION_LIMIT_NOTE],
    })
    if prior is not None:
        before = assert_lifecycle_intact(prior, "the adjudication being corrected")
        if before.get("kind") != "adjudication":
            raise _refuse("wrong-type", "a correction supersedes an adjudication")
        if (before["example_id"] != entry["example_id"]
                or before["input_sha"] != entry["input_sha"]):
            raise _refuse("value-invalid",
                          "a correction supersedes an adjudication of the SAME example: the prior "
                          "record names a different example or a different input")
        _assert_label_transition(before["status"], status,
                                 changed=_target_key(before) != _target_key(entry))
        entry["supersedes"] = before["content_sha"]
        entry["correction"] = {
            "of": before["content_sha"],
            "from_status": before["status"],
            "from_cause": before["cause"],
            "reason": _label_text(correction_reason, "the correction's reason"),
            "note": ("the superseded record is never rewritten. It stays in this example's "
                     "history exactly as it was written, and this record says what was wrong "
                     "with it"),
        }
    elif correction_reason is not None:
        raise _refuse("value-invalid",
                      "a correction reason was given with no prior adjudication to correct")
    return _seal(entry)


def label_state(adjudications):
    """Every adjudication for ONE example -> the current label, its history, its disagreements.

    THE FILE IS THE HISTORY. Corrections append and each one names the digest it supersedes, so
    the chain is reconstructed here rather than trusted: a record nothing supersedes is a HEAD,
    and more than one head means more than one live opinion.

    TWO HEADS THAT AGREE ARE CORROBORATION. Two independent reviewers reaching the same target is
    not a disagreement, and the later record is the current one -- nothing is averaged, and no
    reviewer wins for being a person. Two heads naming different targets are `disputed`, and
    `decision_eval`'s rule applies: a human verdict and an oracle verdict that disagree are a
    disagreement to report, never a vote to settle.

    A DISAGREEMENT IS NOT A TARGET unless the question models ambiguity. That is the one exception
    `TRAINING-DATA.md` allows, and it requires EVERY live head to declare the `ambiguity` shape
    rather than one of them mentioning it.
    """
    entries = []
    for item in adjudications:
        entry = assert_lifecycle_intact(item, "an adjudication")
        if entry.get("kind") != "adjudication":
            raise _refuse("wrong-type",
                          f"label_state reads adjudications; got a {entry.get('kind')!r}")
        entries.append(entry)
    ids = {entry["example_id"] for entry in entries}
    if len(ids) > 1:
        raise _refuse("value-invalid",
                      f"label_state reads one example's history, got {sorted(ids)}")
    ordered = sorted(entries, key=lambda entry: (entry["decided_at"], entry["content_sha"]))
    superseded = {entry["supersedes"] for entry in entries if entry.get("supersedes")}
    heads = [entry for entry in ordered if entry["content_sha"] not in superseded]
    out = {
        "lifecycle_v": LIFECYCLE_VERSION,
        "example_id": sorted(ids)[0] if ids else None,
        "recorded": len(entries),
        "heads": [entry["content_sha"] for entry in heads],
        "corrections": [{"of": entry["supersedes"], "to": entry["content_sha"],
                         "from_status": entry["correction"]["from_status"],
                         "to_status": entry["status"],
                         "reason": entry["correction"]["reason"]}
                        for entry in ordered if entry.get("supersedes")],
        "reviewers": sorted({entry["reviewer"]["id"] for entry in entries}),
        "note": LABEL_VOCABULARY_NOTE,
    }
    if not entries:
        out.update({"status": UNADJUDICATED, "current": None, "disagreement": None,
                    "target": {"eligible": False, "reason": "not-yet-reviewed",
                               "status": UNADJUDICATED, "shape": None, "cause": None,
                               "note": "nobody has reviewed this example"}})
        return out
    disagreement = None
    if len(heads) > 1:
        disagreement = {
            "heads": [entry["content_sha"] for entry in heads],
            "reviewers": sorted({entry["reviewer"]["id"] for entry in heads}),
            "sources": sorted({entry["reviewer"]["source"] for entry in heads}),
            "causes": sorted({str(entry["cause"]) for entry in heads}),
            "shapes": sorted({entry["shape"] for entry in heads}),
            "resolved_by": None,
            "note": None,
        }
    if len(heads) > 1 and len({_target_key(entry) for entry in heads}) > 1:
        models_ambiguity = all(entry["shape"] == "ambiguity" for entry in heads)
        disagreement["note"] = (
            "two live adjudications name different targets. Neither is preferred: a human verdict "
            "and a recorded review verdict that disagree are a disagreement to report, never a "
            "vote to settle")
        out.update({
            "status": "disputed",
            "current": None,
            "disagreement": disagreement,
            "target": {
                "eligible": models_ambiguity,
                "reason": None if models_ambiguity else "disagreement-unresolved",
                "status": "disputed",
                "shape": "ambiguity" if models_ambiguity else None,
                "cause": None,
                "note": ("every live adjudication declares the ambiguity shape, so the "
                         "disagreement IS the target"
                         if models_ambiguity else
                         "an unresolved disagreement is excluded from supervised targets"),
            },
        })
        return out
    current = heads[-1]
    if disagreement is not None:
        disagreement["resolved_by"] = "agreement"
        disagreement["note"] = (
            "two live adjudications reach the same target. That is corroboration rather than a "
            "disagreement, and the later record is the current one")
    eligible = current["status"] == SUPERVISED_TARGET_STATUS
    out.update({
        "status": current["status"],
        "current": current["content_sha"],
        "disagreement": disagreement,
        "target": {
            "eligible": eligible,
            "reason": None if eligible else (current["unresolved_reason"] or "not-yet-reviewed"),
            "status": current["status"],
            "shape": current["shape"],
            "cause": current["cause"],
            "note": None if eligible else
            "a target is only what review evidence supported; this record's did not",
        },
    })
    return out


# ---- the later action, which is a third artifact -------------------------------------------------

def attach_action(record, *, taken, outcome, observed_at, verification=(), alternatives=None,
                  retries=None, intervention=None):
    """What was done AFTER the decision -> a separate `action` artifact.

    IT IS NOT THE INPUT AND IT IS NOT THE LABEL. `observed_at` must place after the decision, so
    an action record can never be back-dated into the evidence the decision was shown; and the
    record carries no cause field, because an action that succeeded is not a diagnosis. D14's
    defect -- a field populated from what merely followed, presented as what the decision
    produced -- is exactly this confusion.

    THERE IS NO SLOT FOR AN OPTIMAL ACTION, AND NO FREE-FORM SLOT AT ALL. `TRAINING-DATA.md`:
    distinguish the observed outcome from an optimal-action label. `taken` is what was attempted
    and `alternatives` is what was permitted, if that is known; neither says what should have been
    done, and nothing here computes it. Every parameter is keyword-only and every one lands in a
    named field, so unlike `adjudicate`'s `claim` there is no caller-keyed object for a key sweep
    to inspect -- which is why none runs here. What enforces the rule is the CLOSED schema, and
    `tests/test_training_data.py` pins this record's exact key set against
    `decision_eval._is_causal_key` and against `_is_input_shaped`, so a later `root_cause` or
    `task_statement` field fails there rather than being swept at run time.

    `outcome` comes from `action_outcome`, so a censored attempt result reads as `unknown` rather
    than as a failure.
    """
    _assert_labelable(record, "an action record")
    if isinstance(alternatives, (str, bytes, Mapping)):
        raise _refuse("wrong-type",
                      f"the permitted alternatives are a sequence of strings, not "
                      f"{type(alternatives).__name__}")
    seen = _instant(observed_at, "the action's observed_at")
    entry = _envelope(record, "action", recorded_at=seen)
    placement = _after_the_decision(seen, record, "the action")
    entry.update({
        "taken": _label_text(taken, "the action taken", limit=MAX_FIELD_CHARS),
        "outcome": _one_of(outcome, ACTION_OUTCOMES, "the action's outcome"),
        "observed_at": seen,
        "placement": placement,
        "verification": _evidence_list(verification, "the action's verification"),
        "alternatives": (None if alternatives is None else
                         [_label_text(item, "a permitted alternative")
                          for item in tuple(alternatives)]),
        "retries": _count(retries, "the action's retries", maximum=2 ** 16),
        "intervention": _label_text(intervention, "the human intervention", optional=True),
        "unknown": sorted(name for name, value in (("alternatives", alternatives),
                                                   ("retries", retries),
                                                   ("intervention", intervention))
                          if value is None),
        "notes": [_de().UNTRIED_ACTION_NOTE, _de().NO_CAUSAL_CLAIM, LABEL_SEPARATE_NOTE],
    })
    return _seal(entry)


# ---- eligibility, retention and revocation ------------------------------------------------------

def transition_eligibility(current, target):
    """One eligibility transition, or a refusal -> the target state.

    The table is the whole rule and it is consulted rather than remembered: `approved` appears in
    one row only, so nothing renews an expired record or reinstates a revoked one, and `revoked`
    leads nowhere.
    """
    _assert_partition(ELIGIBILITY_TRANSITIONS, ELIGIBILITY_STATUSES, ELIGIBILITY_STATUSES,
                      "the eligibility transition table", "training_data.ELIGIBILITY_STATUSES")
    _one_of(current, ELIGIBILITY_STATUSES, "the current eligibility")
    _one_of(target, ELIGIBILITY_STATUSES, "the target eligibility")
    if current == target:
        return target
    if target not in ELIGIBILITY_TRANSITIONS[current]:
        raise _refuse(
            "unknown-value",
            f"{current!r} does not lead to {target!r}; from {current!r} the transitions are "
            f"{ELIGIBILITY_TRANSITIONS[current] or 'none'}. An expired record is not renewed and "
            f"a revoked one is not reinstated")
    return target


def eligibility_state(record, *, now, revocations=()):
    """What this record's use rights are RIGHT NOW -> the state, acted on rather than recorded.

    `now` is required and has no default. A retention decision taken against whatever clock the
    reader happened to hold is not a decision anybody can reproduce, so the instant is passed in
    -- stricter than `bin/memory_store.py`, whose `--now` defaults to today at the CLI while its
    library never reads a clock either.

    THREE THINGS OVERRIDE THE DECLARED STATUS, in this order. A revocation wins outright and is
    terminal. A status that was never `approved` stands as it is -- there is no retention period
    to enforce on rights nobody granted. Otherwise the retention period IS enforced: past
    `expires_on` the state is `expired`, and the expiry date itself is the last usable day. An
    approved record whose `expires_on` could not be computed degrades to `unknown` rather than
    staying approved, because an approval nobody can enforce fails closed like any other unknown.
    """
    assert_intact(record, "the record whose eligibility is being read")
    today = _instant(now, "now")[:10]
    declared = _one_of(record["eligibility"]["status"], ELIGIBILITY_STATUSES,
                       "the record's declared eligibility")
    expires = record["eligibility"]["expires_on"]
    live = []
    for item in revocations:
        entry = assert_lifecycle_intact(item, "a revocation")
        if entry.get("kind") != "revocation":
            raise _refuse("wrong-type",
                          f"eligibility_state reads revocations; got a {entry.get('kind')!r}")
        if entry["example_id"] != record["example_id"]:
            raise _refuse("value-invalid",
                          f"{entry['example_id']} revokes a different example than "
                          f"{record['example_id']}")
        live.append(entry)
    if live:
        state, reason = "revoked", "revoked"
    elif declared != ELIGIBLE_TO_PERSIST:
        state, reason = declared, None
    elif expires is None:
        state, reason = "unknown", "retention-unknown"
    elif today > expires:
        state, reason = "expired", "retention-expired"
    else:
        state, reason = declared, None
    transition_eligibility(declared, state)
    return {
        "lifecycle_v": LIFECYCLE_VERSION,
        "example_id": record["example_id"],
        "declared": declared,
        "state": state,
        "reason": reason,
        "expires_on": expires,
        "checked_at": today,
        "expired": state == "expired",
        "revoked": bool(live),
        "revocations": sorted(entry["content_sha"] for entry in live),
        "terminal": state in ELIGIBILITY_TERMINAL,
        "reaches": list(REVOCATION_REACHES) if live else [],
        "unreached": list(REVOCATION_UNREACHED) if live else [],
        "note": UNLEARNING_NOTE if live else None,
    }


def _dependents(items):
    """The downstream artifacts a revocation names -> what it reaches in each one."""
    if isinstance(items, (str, bytes, Mapping)):
        raise _refuse("wrong-type",
                      f"the dependents are a sequence of {{kind, ref}} entries, not "
                      f"{type(items).__name__}")
    _assert_partition(REVOCATION_REACH, DOWNSTREAM_KINDS, REACH_LEVELS,
                      "the revocation reach table", "training_data.DOWNSTREAM_KINDS")
    built = list(items)
    if len(built) > MAX_DEPENDENTS:
        raise _refuse("bounds-exceeded",
                      f"the revocation names {len(built)} dependents, past the {MAX_DEPENDENTS} "
                      f"one tombstone holds")
    out = []
    for index, item in enumerate(built):
        payload = _closed(item, ("kind", "ref"), f"dependents[{index}]")
        kind = _one_of(payload.get("kind"), DOWNSTREAM_KINDS, f"dependents[{index}].kind")
        pointer = _al().read_ref(payload.get("ref"))
        if pointer is None:
            raise _refuse("not-a-reference",
                          f"dependents[{index}].ref must come from attempt_ledger.make_ref: an "
                          f"artifact nobody can name has not been identified")
        out.append({"kind": kind, "ref": dict(pointer), "ref_gaps": _al().ref_gaps(pointer),
                    "reach": REVOCATION_REACH[kind]})
    return out


def revoke(record, *, revoked_at, reason, by, dependents=()):
    """Withdraw one example's use rights -> a `revocation` artifact.

    WHAT IT REACHES. Every future export of this example refuses; every dependent manifest,
    dataset and readiness report named here is `invalidated`; and every downstream artifact -- a
    checkpoint included -- is IDENTIFIED. `REVOCATION_REACHES` says that as codes.

    WHAT IT DOES NOT REACH. `REVOCATION_UNREACHED` is on this record unconditionally, whatever was
    passed and whatever else holds. A checkpoint trained on this example is named and NOT
    unlearned; copies already exported are not recalled; nothing downstream is rebuilt; and the
    tombstone records the withdrawal rather than proving the bytes are gone. A dependent payload
    whose keys would claim otherwise is refused by `assert_no_unlearning_claim`.

    THE TOMBSTONE IS MINIMAL. It carries the example id, the input digest, who withdrew it, when,
    and a bounded redacted reason -- and no input evidence at all, because a tombstone quoting
    what it withdraws would keep the thing it removes.

    IT IS AVAILABLE IN EVERY STATE. Unlike an adjudication, a revocation is built whatever the
    record's eligibility is: withdrawal has to work precisely when the record is no longer
    approved.
    """
    withdrawn = _instant(revoked_at, "the revocation's revoked_at")
    entry = _envelope(record, "revocation", recorded_at=withdrawn)
    # The sweeps run BEFORE `_dependents`, and the order is the point. `_closed` would refuse a
    # top-level `unlearned` as an unknown field, which is a weaker and less specific answer, and
    # it would not look inside a `ref` at all -- `attempt_ledger.read_ref` reads the three parts
    # it knows and ignores anything else, so a claim nested one level down would sail through.
    assert_no_input_field(dependents, "the revocation's dependents")
    assert_no_unlearning_claim(dependents, "the revocation's dependents")
    rows = _dependents(dependents)
    pointer = _al().read_ref(by)
    if pointer is None:
        raise _refuse("not-a-reference",
                      "the revocation's `by` must come from attempt_ledger.make_ref: an "
                      "unattributed withdrawal cannot be audited")
    cleaned = _rd().redact(_label_text(reason, "the revocation's reason"), limit=MAX_LABEL_CHARS)
    declared = _one_of(record["eligibility"]["status"], ELIGIBILITY_STATUSES,
                       "the record's declared eligibility")
    entry.update({
        "revoked_at": withdrawn,
        "by": dict(pointer),
        "prior_status": declared,
        "status": transition_eligibility(declared, "revoked"),
        "reason": cleaned["text"],
        "redactions": dict(sorted(cleaned["redactions"].items())),
        "dependents": rows,
        "invalidated": sorted(row["ref"]["id"] for row in rows if row["reach"] == "invalidated"),
        "identified": sorted(row["ref"]["id"] for row in rows
                             if row["reach"] == "identified-only"),
        "reaches": list(REVOCATION_REACHES),
        "unreached": list(REVOCATION_UNREACHED),
        "unreached_notes": dict(sorted(REVOCATION_UNREACHED_NOTES.items())),
        "reach_of": dict(sorted(REVOCATION_REACH.items())),
        "notes": [UNLEARNING_NOTE, REDACTION_LIMIT_NOTE],
    })
    return _seal(entry)


def export_eligibility(record, *, now, purpose, destination, store_dir=None,
                       adjudications=None, revocations=None):
    """May this example be exported, right now, for this purpose -> a decision, never a write.

    IT DECIDES AND NOTHING MORE. No file is written, no dataset built and no destination
    contacted; D33 owns exports and this is the gate it has to pass.
    `EXPORT_NOT_ESTABLISHED` rides on every decision saying so.

    AN UNMADE CHECK IS NOT A PASSED ONE. `store_dir` makes this gate read the example's own label
    and revocation files, which is the real check and is cheap because both are keyed by
    `example_id`. Without it a caller must pass what it read; passing NOTHING is not "there were
    none" -- it is `label-not-checked` and `revocation-not-checked`, the distinction
    `workflow_eval.PROMOTION_APPROVAL_BLOCKERS` draws between a missing approval and one nobody
    re-derived.

    UNKNOWN REFUSES. Unknown use rights, an unenforceable retention period, an expired record, a
    revoked one, an unreviewed label, an unresolved one, a live disagreement, an undeclared
    purpose or destination, a purpose that is not the one the scope permitted: each is a code, and
    the export is permitted only when the refusal list is EMPTY.
    """
    refusals = []
    report = integrity(record)
    if not all(value for name, value in report.items() if name.endswith("_ok")):
        # Nothing further is read. A record whose bytes are not the bytes that were digested is
        # not the evidence it claims to be, so its eligibility block and its purpose are not
        # facts to weigh -- and `eligibility_state` would raise on it rather than answer.
        return {
            "lifecycle_v": LIFECYCLE_VERSION,
            "example_id": record.get("example_id") if isinstance(record, Mapping) else None,
            "exportable": False,
            "refusals": ["record-not-intact"],
            "checked": None,
            "eligibility": None,
            "label": None,
            "declared_purpose": purpose,
            "permitted_purpose": None,
            "destination": destination,
            "not_established": list(EXPORT_NOT_ESTABLISHED),
            "not_established_notes": dict(sorted(EXPORT_NOT_ESTABLISHED_NOTES.items())),
            "unreached": [],
            "notes": [UNLEARNING_NOTE, REDACTION_LIMIT_NOTE],
        }
    if store_dir is not None:
        found_labels = read_lifecycle(store_dir, record["example_id"], "adjudication")
        found_revocations = read_lifecycle(store_dir, record["example_id"], "revocation")
        checked = "store"
    else:
        found_labels = None if adjudications is None else list(adjudications)
        found_revocations = None if revocations is None else list(revocations)
        checked = "caller"
    if found_revocations is None:
        refusals.append("revocation-not-checked")
        found_revocations = ()
    if found_labels is None:
        refusals.append("label-not-checked")
        found_labels = ()
    rights = eligibility_state(record, now=now, revocations=found_revocations)
    if rights["expires_on"] is None:
        refusals.append("retention-unknown")
    if rights["state"] != ELIGIBLE_TO_PERSIST:
        refusals.append(f"eligibility-{rights['state']}")
    label = label_state(found_labels)
    if label["status"] == UNADJUDICATED:
        if "label-not-checked" not in refusals:
            refusals.append("label-unadjudicated")
    elif not label["target"]["eligible"]:
        refusals.append("label-disputed" if label["status"] == "disputed" else "label-unresolved")
    permitted = record["eligibility"]["purpose"]
    if purpose is None:
        refusals.append("purpose-not-declared")
    elif _label_text(purpose, "the export purpose", limit=MAX_FIELD_CHARS) != permitted:
        refusals.append("purpose-outside-scope")
    if destination is None:
        refusals.append("destination-not-declared")
    else:
        _label_text(destination, "the export destination")
    unknown = sorted(set(refusals) - set(EXPORT_REFUSALS))
    if unknown:
        raise _refuse("unknown-value",
                      f"this decision produced {unknown}, which EXPORT_REFUSALS does not name")
    return {
        "lifecycle_v": LIFECYCLE_VERSION,
        "example_id": record["example_id"],
        "exportable": not refusals,
        "refusals": sorted(set(refusals)),
        "checked": checked,
        "eligibility": rights,
        "label": label,
        "declared_purpose": purpose,
        "permitted_purpose": permitted,
        "destination": destination,
        "not_established": list(EXPORT_NOT_ESTABLISHED),
        "not_established_notes": dict(sorted(EXPORT_NOT_ESTABLISHED_NOTES.items())),
        "unreached": list(REVOCATION_UNREACHED) if rights["revoked"] else [],
        "notes": [UNLEARNING_NOTE, REDACTION_LIMIT_NOTE],
    }


# ---- lifecycle persistence, through the same store seam -----------------------------------------

def read_lifecycle(store_dir, example_id, kind):
    """Every intact lifecycle record of one kind for one example. Refuses whole.

    A store that does not exist holds nothing, and reading never creates it -- only a write does.
    """
    sp = _sp()
    root = Path(store_dir)
    rel = _example_rel(kind, example_id)  # validated first: an argument is wrong whether or not
    if not root.is_dir():                 # the store happens to exist yet
        return []
    raw = sp.confined_read_bytes(root, rel, what="training lifecycle", missing_ok=True)
    if not raw:
        return []
    out = []
    for number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        entry = _contract().loads(line)
        if not isinstance(entry, dict) or entry.get("v") != LIFECYCLE_VERSION:
            raise _refuse("unknown-value",
                          f"line {number} of {rel} is stamped {(entry or {}).get('v')!r}; this "
                          f"reader reads {LIFECYCLE_VERSION!r}")
        if entry.get("kind") != kind:
            raise _refuse("unknown-value",
                          f"line {number} of {rel} is a {entry.get('kind')!r} in the {kind!r} "
                          f"file")
        out.append(assert_lifecycle_intact(entry, f"line {number} of {rel}"))
    return out


def persist_lifecycle(entry, store_dir):
    """Append one lifecycle record -> `{"written", "path", "content_sha", "reason"}`.

    APPEND-ONLY, WHICH IS WHAT MAKES CORRECTION HISTORY REAL. A correction never overwrites the
    record it supersedes; it lands beside it and names its digest, so the history IS the file and
    cannot be quietly rewritten into a tidier one.

    IDEMPOTENT BY CONTENT DIGEST: recording the same adjudication twice writes once.
    """
    assert_lifecycle_intact(entry, "the lifecycle record being persisted")
    kind = entry["kind"]
    sp = _sp()
    root = Path(store_dir)
    rel = _example_rel(kind, entry["example_id"])
    existing = read_lifecycle(root, entry["example_id"], kind)
    for other in existing:
        if other["content_sha"] == entry["content_sha"]:
            return {"written": False, "path": str(root / rel),
                    "content_sha": entry["content_sha"], "reason": "already-recorded"}
    if len(existing) >= MAX_LIFECYCLE_ENTRIES:
        raise _refuse(
            "bounds-exceeded",
            f"{entry['example_id']} already carries {len(existing)} {kind} records, the "
            f"{MAX_LIFECYCLE_ENTRIES} one example holds. The append is refused rather than the "
            f"oldest dropped: losing correction history is the one thing this file may not do")
    data = (canonical(entry) + "\n").encode("utf-8")
    if len(data) > MAX_RECORD_BYTES:
        raise _refuse("bounds-exceeded", f"refusing a {len(data)}-byte {kind} line")
    _rt().ensure_private(root)
    sp.confined_append_bytes(root, rel, data, what=f"training {kind}")
    return {"written": True, "path": str(root / rel), "content_sha": entry["content_sha"],
            "reason": None}


# ==================================================================================================
#  D33 -- GROUPED DATASET SPLITS AND REPRODUCIBLE LOCAL EXPORTS
# ==================================================================================================
#
# ONE PARTITION AUTHORITY, READ AT CALL TIME. `bin/workflow_eval.py` owns the partitions, their
# roles, defect grouping, leak screening and the exposure log. This section owns NONE of that: it
# names exactly one partition (`TRAINABLE_PARTITION`) and then asks that module, at call time,
# whether the partition still exists, still declares itself neither held-out nor single-use, and
# which of the others are. `dataset_rules` DERIVES every list it reports from `PARTITION_ROLES`
# rather than listing one here, so marking `development` held-out upstream refuses this exporter
# instead of quietly re-labelling final-audit material as training material.
#
# WHY `require_held_out` IS NOT THE CALL. That function is the controller for citing a partition as
# HELD-OUT evidence, and it refuses `development` by design -- development's role is fitting. An
# export draws from the one partition a fit may legitimately happen in, so the question it has to
# ask is the mirror image: has this item been seen for something that is NOT development's own
# purpose, or retired? Both answers come from `exposure_state`, the owner's own reader, and the
# purpose compared against is `PARTITION_ROLES[TRAINABLE_PARTITION]["purpose"]` read at call time --
# never a string written down here.
#
# RELATED ATTEMPTS CANNOT CROSS A SPLIT, AND THE REFUSAL IS THE OWNER'S OWN FINDING. One defect,
# one group, one partition is `workflow_eval`'s invariant, and `verify_manifest` is what detects a
# group split across partitions. `build_dataset` calls it and refuses the WHOLE export on any
# finding: a manifest whose groups are split cannot place anything safely, and picking an
# "exportable subset" out of a corrupt manifest is exactly how a held-out result comes to have been
# solved already, in full view, in development.
#
# THIS IS THE TASK THAT PREVENTS. `export_eligibility` DECIDES: it returns refusal codes and carries
# `enforcement-not-provided` unconditionally, because a process that ignores its answer is not
# stopped by it. `build_dataset` is the caller that ACTS on that decision -- a record whose refusal
# list is non-empty never reaches a payload line -- so for the one route this module owns, a local
# JSONL export, the gate is enforced rather than merely reported. It still prevents nothing about a
# process that reads the store directly; that remains the store's own permissions and
# `bin/exec_policy.py`'s question.
#
# TWO FILES, AND THE SEPARATION IS THE SCHEMA. `payload.jsonl` is the model input and its target;
# `audit.jsonl` is provenance, eligibility, label rationale, reviewer, resources and redaction
# counts. `PAYLOAD_FIELDS` and `AUDIT_FIELDS` are closed and share exactly ONE name -- the join key
# -- and an input entry loses its `provenance`, its redaction counts and its lengths on the way into
# a payload line. A record's bookkeeping must not become a feature: if the provenance is in the
# input, a model can read the answer off the bookkeeping.
#
# NO ACTION OUTCOME IS EXPORTED, ON PURPOSE. D32's `attach_action` accepts an `ACTION_OUTCOMES`
# member directly, so an action record does not say whether its outcome was DERIVED through
# `action_outcome()` or DECLARED by its caller. Rather than present a declared field as a measured
# one, this exporter does not read action records at all: the only target it writes is the
# adjudicated cause. Learning action choice is a different question needing its own validated
# labels (`TRAINING-DATA.md`), and giving it one would need an `outcome_basis` on the action record
# first. `PAYLOAD_FIELDS` and `AUDIT_FIELDS` are pinned in `tests/test_training_data.py` so a later
# outcome field fails there rather than shipping as a measurement.
#
# NOTHING HERE TRAINS, TRANSFERS, OR WRITES SOMEBODY ELSE'S STORE. `build_dataset` writes nothing at
# all; `write_dataset` creates three create-once files under the training store through
# `bin/safe_paths.py`. The evals store is NOT written: recording the draw in `workflow_eval`'s own
# exposure log is that module's writer's business, and `exposure-not-recorded-in-the-eval-store`
# rides on every manifest saying so rather than this module growing a second writer.

#: The exported dataset's own schema, registered in `release_gate.VERSION_SOURCES`. ONE constant for
#: the manifest, the payload line and the audit line -- the precedent is `LIFECYCLE_VERSION`, which
#: stamps three artifacts revised together. The exporter and the record shape move together too, so
#: the manifest reports this same string as its exporter version rather than carrying a second
#: number that could drift from the shape it describes.
DATASET_VERSION = "polytropos.training-dataset/1"

#: Where exports land inside the training store, one directory per content-addressed dataset id.
DATASET_DIR = "datasets"

#: The three files one export writes. Closed: a reader looks for these names, and a fourth file
#: would need its own digest row in `content_identities`.
DATASET_FILES = {"payload": "payload.jsonl", "audit_metadata": "audit_metadata.jsonl",
                 "manifest": "manifest.json"}

#: The ONE partition this exporter may draw from. Named here and verified against
#: `workflow_eval.PARTITION_ROLES` at call time by `dataset_rules`; every other partition is refused
#: by inequality with this name, and WHY it is refused -- held-out, single-use, quarantined -- is
#: read off the owner's table rather than listed here.
TRAINABLE_PARTITION = "development"

#: How many examples one export may carry. Past it the export is refused rather than trimmed: an
#: export silently capped is a dataset whose manifest describes material it does not contain, and
#: the caller decides which bounded slice to export.
MAX_DATASET_EXAMPLES = 2_000

#: What a model input line carries. CLOSED, and it shares exactly one name with `AUDIT_FIELDS`.
PAYLOAD_FIELDS = ("example_id", "question", "input", "target")

#: What survives of one input entry into a payload line: the text the decision was shown and when
#: it was observed. `provenance`, `redactions`, `truncated` and `original_length` are the record's
#: bookkeeping and stay in the audit file.
PAYLOAD_ENTRY_KEYS = ("text", "observed_at")

#: What an audit line carries. CLOSED. `example_id` is the join key and the ONLY name it shares with
#: `PAYLOAD_FIELDS`; everything else here is provenance a model never sees.
AUDIT_FIELDS = ("example_id", "input_sha", "content_sha", "captured_at", "prediction_at",
                "boundary", "sources", "source_gaps", "placement", "eligibility", "label",
                "operational_observation", "input_provenance", "reproducibility",
                "resources", "redaction", "unknown", "versions")

#: Why a record was left out, over and above every code `EXPORT_REFUSALS` already names. Closed, and
#: `tests/test_training_data.py` constructs a case for every member: a code nothing can emit reads
#: as a guard and is not one. `exclusion_codes` is the union, and a name declared on both sides
#: refuses rather than one shadowing the other.
DATASET_EXCLUSIONS = ("source-reference-missing", "source-not-in-manifest", "source-ambiguous",
                      "partition-not-trainable", "partition-held-out", "partition-single-use",
                      "partition-quarantined", "leak-screened-positive", "item-retired",
                      "item-exposed-elsewhere", "exposure-not-checked",
                      "input-after-the-decision", "input-placement-unknown", "input-truncated",
                      "audit-identity-in-payload", "target-not-single-headed")

#: What an export does NOT establish, carried unconditionally on every manifest, for the reason
#: `EXPORT_NOT_ESTABLISHED` is unconditional: a reader must be able to check that no dataset ever
#: claimed more, and no branch below can discharge one of these by passing some other check.
DATASET_NOT_ESTABLISHED = ("digest-identifies-content-not-provenance", "access-not-enforced",
                           "exposure-not-recorded-in-the-eval-store",
                           "training-sufficiency-not-established",
                           "no-transfer-and-no-training-performed")

DATASET_NOT_ESTABLISHED_NOTES = {
    "digest-identifies-content-not-provenance":
        "the manifest's digest identifies these bytes and detects a change to them. It says "
        "nothing about whether the inputs were real: a correct digest is computable over a forged "
        "record, so a matching digest establishes that nothing was altered after the export and "
        "never that what was exported was observed",
    "access-not-enforced":
        "the manifest identifies content. It does not restrict who may read these files and it is "
        "not an isolation boundary: the store's 0700/0600 modes and bin/exec_policy.py's answer "
        "are what confine a reader, and either may be absent on this host",
    "exposure-not-recorded-in-the-eval-store":
        "this export READ workflow_eval's exposure log and wrote nothing to it. The draw is "
        "recorded here -- source manifest, item ids, partition -- and an operator who wants it in "
        "that module's own log calls workflow_eval.record_exposure themselves. The evals store has "
        "one writer and this is not it",
    "training-sufficiency-not-established":
        "the counts below describe what was exported. They are not evidence that the dataset is "
        "large enough, balanced enough or representative enough to train anything: no minimum "
        "sample count is asserted anywhere, and a fixture's counts are not a readiness claim",
    "no-transfer-and-no-training-performed":
        "no destination was contacted, no byte left this machine, and no model was trained, "
        "fine-tuned or evaluated. `destination` is a declared string compared against the scope's "
        "permitted purpose, and D34 owns the readiness report that says what is still missing",
}

AUDIT_SEPARATION_NOTE = (
    "the model input and the audit metadata are two files, and the schemas that build them share "
    "exactly one key -- the example id they join on. Provenance, reviewer identity, label "
    "rationale, eligibility, resource bases and redaction counts are audit metadata: in a model's "
    "input they would be features, and a model that can read the bookkeeping can read the answer "
    "off it")

DETERMINISM_NOTE = (
    "the same records, the same source manifest and the same declared provenance produce "
    "byte-identical files. Nothing here reads a clock, a home directory, a path or a set's "
    "iteration order: `built_at` and `built_by` are passed in and sit OUTSIDE the digest, every "
    "collection is sorted before it is serialised, and the canonical form is the decision "
    "contract's own")

GROUPING_UNCERTAINTY_NOTE = (
    "the defect key and the group id are workflow_eval's, copied verbatim. That module does not "
    "report WHICH of its fallbacks produced a key -- an issue, a fix commit, the patched paths, or "
    "the task's own id for a group of one -- so this manifest records the key rather than "
    "classifying the detection method, and a group of one is recorded as a group of one rather "
    "than as a confident grouping")


# ---- the partition rules, derived from their owner rather than restated -------------------------

def dataset_rules():
    """Which partitions this exporter may draw from -> derived from `PARTITION_ROLES` at call time.

    Every list here is COMPUTED from `workflow_eval.PARTITION_ROLES`, so nothing in this module
    remembers which partitions are held out or single-use. Three things refuse rather than degrade:
    a `PARTITIONS` tuple that is no longer an exact partition of that table, the disappearance of
    `TRAINABLE_PARTITION` from it, and that partition declaring itself held-out or single-use. The
    last is the one that matters -- the day somebody marks `development` held out, an exporter that
    trusted a string here would spend the held-out material instead of refusing.
    """
    wf = _wf()
    roles = dict(wf.PARTITION_ROLES)
    names = tuple(wf.PARTITIONS)
    missing = sorted(set(names) - set(roles))
    extra = sorted(set(roles) - set(names))
    if missing or extra:
        raise _refuse("unknown-value",
                      f"workflow_eval.PARTITIONS and PARTITION_ROLES disagree: unmapped "
                      f"{missing or 'none'}, unknown {extra or 'none'}. That module owns both, and "
                      f"an exporter cannot place material against a table with a hole in it")
    if TRAINABLE_PARTITION not in roles:
        raise _refuse(
            "unknown-value",
            f"workflow_eval.PARTITION_ROLES no longer declares {TRAINABLE_PARTITION!r}, which is "
            f"the one partition this exporter draws from. That module owns the partitions; this "
            f"one owns which single partition is trainable, and a rename is reconciled here")
    role = dict(roles[TRAINABLE_PARTITION])
    if role.get("held_out") or role.get("single_use"):
        raise _refuse(
            "value-invalid",
            f"{TRAINABLE_PARTITION!r} now declares held_out={role.get('held_out')!r} "
            f"single_use={role.get('single_use')!r}. Training from held-out or single-use material "
            f"spends the evidence a promotion or audit decision rests on, so this exporter refuses "
            f"rather than draws from it")
    return {
        "owner": "bin/workflow_eval.py:PARTITION_ROLES",
        "partitions": list(names),
        "trainable": TRAINABLE_PARTITION,
        "trainable_purpose": _label_text(role.get("purpose"),
                                         f"{TRAINABLE_PARTITION}'s exposure purpose"),
        "refused": sorted(set(names) - {TRAINABLE_PARTITION}),
        "held_out": sorted(name for name in names if (roles[name] or {}).get("held_out")),
        "single_use": sorted(name for name in names if (roles[name] or {}).get("single_use")),
        "fitting": sorted(name for name in names if (roles[name] or {}).get("fitting")),
        "quarantine_bucket": wf.QUARANTINE,
        "exposure_purposes": list(wf.EXPOSURE_PURPOSES),
        "grouping": wf.GROUPING_RULE,
        "assignment": wf.ASSIGNMENT_RULE,
        "enforcement": wf.NOT_ENFORCEMENT_LABEL,
        "roles": _copy(roles),
        "note": GROUPING_UNCERTAINTY_NOTE,
    }


def exclusion_codes():
    """Every code a dataset exclusion may carry -> D32's export refusals plus D33's own, sorted.

    `EXPORT_REFUSALS` is read here rather than copied, because the eligibility decision is D32's and
    this module records its answer verbatim. A name declared on both sides refuses: one code, one
    meaning, and a collision would leave a reader unable to tell which check emitted it.
    """
    owner = tuple(EXPORT_REFUSALS)
    overlap = sorted(set(owner) & set(DATASET_EXCLUSIONS))
    if overlap:
        raise _refuse(
            "duplicate-entry",
            f"{overlap} are declared both in EXPORT_REFUSALS and in DATASET_EXCLUSIONS. One code, "
            f"one owner: reconcile them rather than letting one shadow the other")
    return tuple(sorted(owner + DATASET_EXCLUSIONS))


def _dataset_id(value):
    """A dataset id, checked as an identity AND as a single filename component.

    HONEST ABOUT WHICH CHECK BITES. The regex is strictly narrower than `safe_paths.SAFE_ID_RE`, so
    `validate_id` cannot be the thing that refuses `../escape` -- the shape check already did. It is
    called anyway because the repository's rule is that a filename component DERIVED FROM DATA goes
    through `safe_paths`, and it is what would still hold if this id format ever widened. The same
    pairing is `_example_id`'s.
    """
    text = _label_text(value, "a dataset id", limit=64)
    if not re.fullmatch(r"ds-[0-9a-f]{16}", text):
        raise _refuse("value-invalid",
                      f"a dataset id is 'ds-' and 16 hex characters derived from the manifest "
                      f"digest, got {text!r}")
    return _sp().validate_id(text, "a dataset id")


# ---- the two lines one example produces ---------------------------------------------------------

def _payload_line(record, target):
    """One model input and its target. The audit metadata is NOT in it (`AUDIT_SEPARATION_NOTE`).

    The input is rebuilt entry by entry against `PAYLOAD_ENTRY_KEYS` rather than copied, so the drop
    is structural: a stored entry carries `provenance`, `redactions`, `truncated` and
    `original_length`, and none of those has a key to land in here. An absent field stays `None`
    rather than becoming `[]`, because "nobody recorded what it was shown" and "it was shown none"
    are different facts and a training input must not blur them.
    """
    block = {}
    for field in INPUT_FIELDS:
        offered = record["input"][field]
        if offered is None:
            block[field] = None
            continue
        block[field] = [{key: entry.get(key) for key in PAYLOAD_ENTRY_KEYS} for entry in offered]
    line = {
        "example_id": record["example_id"],
        "question": {
            "qualified_id": record["question"]["qualified_id"],
            "spec": _copy(record["question"]["spec"]),
        },
        "input": block,
        "target": target,
    }
    return _closed(line, PAYLOAD_FIELDS, "the payload line")


def _input_provenance(record):
    """Everything an input entry carries that a model input must not -> the audit file's copy.

    THE SEPARATION LOSES NOTHING. `_payload_line` drops each entry's source, artifact digest,
    placement, redaction counts and lengths; they land here, in the same order, so an auditor can
    still say which artifact every retained line came from and what was redacted out of it.
    `TRAINING-DATA.md` requires field provenance and evidence artifact hashes -- it just requires
    them somewhere a model's input is not.
    """
    block = {}
    for field in INPUT_FIELDS:
        offered = record["input"][field]
        if offered is None:
            block[field] = None
            continue
        block[field] = [{
            "source": (entry.get("provenance") or {}).get("source"),
            "artifact_sha": (entry.get("provenance") or {}).get("artifact_sha"),
            "placement": entry.get("placement"),
            "redactions": _copy(entry.get("redactions") or {}),
            "truncated": bool(entry.get("truncated")),
            "original_length": entry.get("original_length"),
        } for entry in offered]
    return block


def _target_of(head):
    """The supervised target this example carries -> shape, cause, competing causes.

    Only what review ESTABLISHED. `adjudicate` writes `cause` from the supported target and from
    nowhere else, and the rationale behind it -- the evidence, the reviewer, the claim somebody
    proposed, the unresolved reason -- stays in the audit file where a model never sees it.
    """
    return {
        "shape": head["shape"],
        "cause": head["cause"],
        "contributing": [row["cause"] for row in head["contributing"]],
        "taxonomy_v": head["taxonomy_v"],
    }


def _label_audit(head, state):
    """The label's provenance: who, when, on what evidence, and what it does not establish."""
    return {
        "head": head["content_sha"],
        "status": state["status"],
        "shape": head["shape"],
        "cause": head["cause"],
        "contributing": [{"cause": row["cause"], "supported": row["supported"]}
                         for row in head["contributing"]],
        "unresolved_reason": head["unresolved_reason"],
        "reviewer": _copy(head["reviewer"]),
        "decided_at": head["decided_at"],
        "evidence": [{"source": item["source"], "weight": item["weight"],
                      "ref": _copy(item["ref"]), "ref_gaps": list(item["ref_gaps"])}
                     for item in head["evidence"]],
        "support": _copy(head["support"]),
        "supersedes": head["supersedes"],
        "corrections": len(state["corrections"]),
        "reviewers": list(state["reviewers"]),
        "taxonomy_v": head["taxonomy_v"],
        "not_established": list(head["not_established"]),
        "note": LABEL_VOCABULARY_NOTE,
    }


def _audit_line(record, *, decision, placement, label):
    """Everything about one example that is provenance rather than the evidence itself."""
    line = {
        "example_id": record["example_id"],
        "input_sha": record["input_sha"],
        "content_sha": record["content_sha"],
        "captured_at": record["captured_at"],
        "prediction_at": record["prediction_at"],
        "boundary": _copy(record["boundary"]),
        "sources": _copy(record["sources"]),
        "source_gaps": _copy(record["source_gaps"]),
        "placement": placement,
        "eligibility": _copy(decision["eligibility"]),
        "label": label,
        "operational_observation": _copy(record["candidate_cause"]),
        "input_provenance": _input_provenance(record),
        "reproducibility": _copy(record["reproducibility"]),
        "resources": _copy(record["resources"]),
        "redaction": _copy(record["redaction"]),
        "unknown": list(record["unknown"]),
        "versions": {
            "snapshot": SNAPSHOT_VERSION,
            "taxonomy": TAXONOMY_VERSION,
            "lifecycle": LIFECYCLE_VERSION,
            "dataset": DATASET_VERSION,
            "contract": _contract().CONTRACT_VERSION,
            "eval_manifest": _wf().MANIFEST_VERSION,
            "question": record["question"]["qualified_id"],
            "question_digest": record["question"]["digest"],
        },
    }
    return _closed(line, AUDIT_FIELDS, "the audit line")


def _placement_codes():
    """The two inadmissible placements -> their exclusion codes, derived from the owner.

    `decision_eval.FACT_PLACEMENTS` has three members and this module admits exactly one of them.
    The other two are the two refusals -- and which string is which is re-derived by ASKING that
    module (a fact from later, and a fact nobody can place) rather than by spelling either one
    here. A literal would be a second copy of its vocabulary; deriving it means the day that
    module grows a fourth placement, this refuses instead of quietly reading the new one as
    "unknown".
    """
    de = _de()
    later = de.placement("2000-01-02T00:00:00Z", "2000-01-01T00:00:00Z")
    unplaceable = de.placement(None, None)
    answers = {ADMISSIBLE_PLACEMENT, later, unplaceable}
    if len(answers) != 3 or answers != set(de.FACT_PLACEMENTS):
        raise _refuse(
            "unknown-value",
            f"decision_eval.FACT_PLACEMENTS is {sorted(de.FACT_PLACEMENTS)} and the three answers "
            f"this module can derive are {sorted(answers)}. That module owns placement; this one "
            f"owns which answer is admissible in a training input, and a placement nobody mapped "
            f"would be read as one of the two it is not")
    return {later: "input-after-the-decision", unplaceable: "input-placement-unknown"}


def _input_refusals(record):
    """Every reason this record's retained input is not admissible evidence -> codes.

    THE ROUTE IS REAL, AND IT IS THE ONE D18 NAMES. `snapshot()` refuses a late entry at capture,
    but `assert_intact` only checks that the bytes are the bytes that were digested -- and a caller
    can compute a correct digest over a forged record. So placement is re-derived HERE, through
    `decision_eval.placement`, over the record that is actually about to be exported. An entry from
    after the decision is the future answer leaking into the problem statement, and an entry whose
    instant nobody can place is not evidence that it was available either.

    A truncated entry is refused for D31's own reason: an example cut in half is a corrupt example,
    and `redact` can shorten a field even inside the length bound when a placeholder is longer than
    what it replaced.
    """
    inadmissible = _placement_codes()
    codes = []
    for field in INPUT_FIELDS:
        offered = record["input"][field]
        if offered is None:
            continue
        if not isinstance(offered, list):
            raise _refuse("wrong-type",
                          f"input.{field} of {record['example_id']} is "
                          f"{type(offered).__name__}, not a list of entries")
        for entry in offered:
            if not isinstance(entry, Mapping):
                raise _refuse("wrong-type",
                              f"an entry of input.{field} is {type(entry).__name__}, not an object")
            where = _de().placement(entry.get("observed_at"), record["prediction_at"])
            if where != ADMISSIBLE_PLACEMENT:
                codes.append(inadmissible[where])
            if entry.get("truncated"):
                codes.append("input-truncated")
    return codes


def _audit_identity_hits(payload, record, head, item_id, group_id):
    """Audit identifiers that reached the model input verbatim -> the ones found, sorted.

    THE ROUTE IS REAL AND IT IS NOT THIS MODULE'S OWN CONSTRUCTION. `_payload_line` builds from a
    closed allowlist, so no audit FIELD can arrive -- that part is the schema's job. What a schema
    cannot stop is a VALUE: the question's wording and rubric are the caller's text, copied verbatim
    out of the record, and so is every retained entry. A question that quotes the group id, the
    manifest item id or the adjudication's digest has put the bookkeeping into the input, and a
    model that can read the bookkeeping can read the answer off it.

    Only content-derived identifiers are checked. The reviewer's id and the partition's name are
    caller-chosen words with innocent readings -- a decision really can have been shown the word
    "development" -- so searching for those would refuse honest examples, and what keeps them out
    is the schema rather than a search.
    """
    blob = canonical(payload)
    identities = {item_id, group_id, head["content_sha"], record["content_sha"]}
    return sorted(str(value) for value in identities
                  if value and len(str(value)) >= 8 and str(value) in blob)


# ---- the export itself, which writes nothing -----------------------------------------------------

def build_dataset(records, *, eval_manifest, store_dir, exposure_dir, now, purpose, destination,
                  built_at, built_by, partition=TRAINABLE_PARTITION, parent=None):
    """Eligible development records -> one immutable, content-addressed local dataset. No write.

    NOTHING IS WRITTEN AND NOTHING IS CONTACTED. This reads the training store (each example's own
    label and revocation files, keyed by example id) and the evals store's exposure log, and
    produces the bytes of three files. `write_dataset` is the writer; no path is created here, no
    destination is reached, and there is no trainer in this module to reach.

    `store_dir` IS REQUIRED, which is what makes this the task that PREVENTS. `export_eligibility`
    without it answers `label-not-checked` and `revocation-not-checked` rather than an all-clear;
    demanding it means those two codes cannot arise through this path at all, because the gate
    always reads the example's own label and revocation files. A record whose refusal list is
    non-empty never reaches a payload line.

    `built_at` and `built_by` have no defaults. A clock read here would make the same material
    export to different bytes on two runs, so provenance is declared by the caller and sits OUTSIDE
    the digest -- the dataset id is a pure function of the material, and re-exporting the same
    material a year later gets the same id.

    WHAT REFUSES OUTRIGHT, rather than excluding one record: a partition that is not the trainable
    one, a source manifest that is not a `workflow_eval` manifest, ANY finding from
    `verify_manifest` (a split group above all), a record whose `example_id` is not an example id,
    and two records claiming one example id with different content. Everything else is a per-record
    exclusion with its own code, counted and named in the manifest.
    """
    rules = dataset_rules()
    if partition != rules["trainable"]:
        raise _refuse(
            "value-invalid",
            f"{partition!r} is not the partition this exporter draws from. Only "
            f"{rules['trainable']!r} may be trained from: {rules['held_out']} are held-out "
            f"evidence, {rules['single_use']} is single-use, and a training export that touches "
            f"either spends what a promotion or audit decision rests on")
    wf = _wf()
    if not isinstance(eval_manifest, Mapping) or eval_manifest.get("v") != wf.MANIFEST_VERSION:
        raise _refuse(
            "not-a-reference",
            f"the source manifest must be a {wf.MANIFEST_VERSION} manifest from "
            f"workflow_eval.build_manifest: that module owns grouping and partition assignment, "
            f"and this exporter places nothing on its own")
    findings = wf.verify_manifest(eval_manifest)
    if findings:
        kinds = sorted({str(finding.get("kind")) for finding in findings})
        raise _refuse(
            "value-invalid",
            f"the source manifest carries {len(findings)} finding(s) from "
            f"workflow_eval.verify_manifest ({', '.join(kinds)}), so nothing is exported from it. "
            f"A group split across partitions is the one that matters: related variants of one "
            f"defect on opposite sides of a split mean a held-out result was already solved, in "
            f"full view, in development -- and choosing an exportable subset of a corrupt manifest "
            f"is how that goes unnoticed")
    if store_dir is None:
        raise _refuse(
            "missing-field",
            "an export reads each example's own label and revocation files, so the training store "
            "is required. Passing none is not 'there were none' -- it is the unmade check "
            "export_eligibility reports as label-not-checked, and an unmade check is not a passed "
            "one")
    built = _instant(built_at, "built_at")
    author = _label_text(built_by, "built_by")
    checked_at = _instant(now, "now")
    lineage = None if parent is None else _dataset_id(parent)
    source = eval_manifest["content"]
    by_task = {}
    for iid in sorted(source["items"]):
        by_task.setdefault(str(source["items"][iid].get("task_id")), []).append(iid)
    exposure = None if exposure_dir is None else wf.exposure_state(exposure_dir, eval_manifest)

    offered = 0
    duplicates = 0
    unique = {}
    for record in records:
        offered += 1
        if not isinstance(record, Mapping) or record.get("v") != SNAPSHOT_VERSION:
            raise _refuse("not-a-reference",
                          f"an exported record is a {SNAPSHOT_VERSION} snapshot, got "
                          f"{(record or {}).get('v')!r}")
        eid = _example_id(record.get("example_id"))
        if eid not in unique:
            unique[eid] = record
            continue
        if unique[eid].get("content_sha") != record.get("content_sha"):
            raise _refuse(
                "duplicate-entry",
                f"{eid} was offered twice with different content. One id names one input, so this "
                f"is two records claiming one example rather than one record offered twice, and "
                f"collapsing them would silently pick one")
        duplicates += 1
    if len(unique) > MAX_DATASET_EXAMPLES:
        raise _refuse("bounds-exceeded",
                      f"{len(unique)} examples were offered, past the {MAX_DATASET_EXAMPLES} one "
                      f"export carries. It is refused rather than trimmed: a manifest describing "
                      f"material its files do not contain is worse than a second export")

    vocabulary = set(exclusion_codes())
    payload_lines, audit_lines, examples, excluded = [], [], [], []
    groups, drawn_items = {}, set()
    for eid in sorted(unique):
        record = unique[eid]
        decision = export_eligibility(record, now=now, purpose=purpose, destination=destination,
                                      store_dir=store_dir)
        codes = list(decision["refusals"])
        if "record-not-intact" in codes:
            # Nothing further is read, for `export_eligibility`'s own reason: a record whose bytes
            # are not the bytes that were digested has no fields worth weighing.
            excluded.append({"example_id": eid, "refusals": sorted(set(codes)),
                             "label_status": None, "group": None, "item": None})
            continue
        item_id = group_id = group_key = home = None
        ref = (record["sources"] or {}).get("task_ref")
        if not isinstance(ref, Mapping) or not ref.get("id"):
            codes.append("source-reference-missing")
        else:
            matches = by_task.get(str(ref["id"]), [])
            if not matches:
                codes.append("source-not-in-manifest")
            elif len(matches) > 1:
                codes.append("source-ambiguous")
            else:
                item_id = matches[0]
                item = source["items"][item_id]
                group_id = item.get("group")
                group_key = (source["groups"].get(group_id) or {}).get("key")
                home = item.get("partition")
                if home != partition:
                    codes.append("partition-not-trainable")
                    if home == rules["quarantine_bucket"]:
                        codes.append("partition-quarantined")
                    if home in rules["held_out"]:
                        codes.append("partition-held-out")
                    if home in rules["single_use"]:
                        codes.append("partition-single-use")
                if item.get("leaks"):
                    codes.append("leak-screened-positive")
        if exposure is None:
            codes.append("exposure-not-checked")
        elif item_id is not None:
            seen = exposure["items"].get(item_id) or {}
            if seen.get("retired"):
                codes.append("item-retired")
            if any(purpose_seen != rules["trainable_purpose"]
                   for purpose_seen in seen.get("purposes") or []):
                codes.append("item-exposed-elsewhere")
        codes.extend(_input_refusals(record))
        label = decision["label"]
        head = None
        if label["target"]["eligible"]:
            # ONE lookup rather than two checks. A label D32 calls eligible has a target -- but a
            # DISPUTED one that models ambiguity has no single head (`label_state` leaves `current`
            # None), and there is then no adjudication to take a shape and a cause from. The lookup
            # finds none and says so. A separate `current is None` branch was removed for being a
            # second spelling of the same fact: deleting it changed nothing any test could see.
            history = read_lifecycle(store_dir, eid, "adjudication")
            head = next((entry for entry in history
                         if entry["content_sha"] == label["current"]), None)
            if head is None:
                codes.append("target-not-single-headed")
        # else: one of D32's own label-* codes already named why there is no target
        if not codes:
            payload = _payload_line(record, _target_of(head))
            if _audit_identity_hits(payload, record, head, item_id, group_id):
                codes.append("audit-identity-in-payload")
        unknown = sorted(set(codes) - vocabulary)
        if unknown:
            raise _refuse("unknown-value",
                          f"this export produced {unknown}, which neither EXPORT_REFUSALS nor "
                          f"DATASET_EXCLUSIONS names")
        if codes:
            excluded.append({"example_id": eid, "refusals": sorted(set(codes)),
                             "label_status": label["status"], "group": group_id, "item": item_id})
            continue
        audit = _audit_line(record, decision=decision, label=_label_audit(head, label),
                            placement={
                                "item": item_id,
                                "group": group_id,
                                "group_key": group_key,
                                "partition": home,
                                "source_manifest": wf.manifest_ref(eval_manifest),
                                "grouping_owner": rules["owner"],
                                "grouping": rules["grouping"],
                                "assignment": rules["assignment"],
                                "note": GROUPING_UNCERTAINTY_NOTE,
                            })
        for what, line in (("payload", payload), ("audit_metadata", audit)):
            size = len((canonical(line) + "\n").encode("utf-8"))
            if size > MAX_RECORD_BYTES:
                raise _refuse("bounds-exceeded",
                              f"refusing a {size}-byte {what} line for {eid}")
        payload_lines.append(payload)
        audit_lines.append(audit)
        drawn_items.add(item_id)
        examples.append({
            "example_id": eid,
            "input_sha": record["input_sha"],
            "content_sha": record["content_sha"],
            "item": item_id,
            "group": group_id,
            "group_key": group_key,
            "label_head": head["content_sha"],
            "label_taxonomy_v": head["taxonomy_v"],
            "shape": head["shape"],
            "cause": head["cause"],
            "payload_sha": _sha(payload),
            "audit_metadata_sha": _sha(audit),
        })
        row = groups.setdefault(group_id, {
            "group": group_id, "key": group_key, "partition": home,
            "items": sorted((source["groups"].get(group_id) or {}).get("items") or []),
            "drawn": [], "examples": []})
        if item_id not in row["drawn"]:
            row["drawn"].append(item_id)
        row["examples"].append(eid)

    for row in groups.values():
        row["drawn"] = sorted(row["drawn"])
        row["examples"] = sorted(row["examples"])
        row["size"] = len(row["items"])
        row["solo"] = len(row["items"]) == 1
    payload_blob = "".join(canonical(line) + "\n" for line in payload_lines).encode("utf-8")
    audit_blob = "".join(canonical(line) + "\n" for line in audit_lines).encode("utf-8")
    by_code, by_status, by_target = {}, {}, {}
    for row in excluded:
        by_status[str(row["label_status"])] = by_status.get(str(row["label_status"]), 0) + 1
        for code in row["refusals"]:
            by_code[code] = by_code.get(code, 0) + 1
    for row in examples:
        key = f"{row['shape']}/{row['cause']}"
        by_target[key] = by_target.get(key, 0) + 1

    content = {
        "v": DATASET_VERSION,
        "exporter": {
            "module": "bin/training_data.py",
            "version": DATASET_VERSION,
            "note": "the exporter and this record shape are ONE version, revised together, so a "
                    "reader holding a line knows which exporter wrote it",
        },
        "partition": partition,
        "parent": lineage,
        "files": dict(sorted(DATASET_FILES.items())),
        "selection": {
            "policy": "all-eligible",
            "partition": partition,
            "sampled": False,
            "note": "every eligible record in the trainable partition is exported and nothing is "
                    "sampled, so the counts below are the whole eligible set rather than a draw "
                    "from it. A sampling policy would have to be declared and recorded here",
        },
        "rules": {
            "trainable": rules["trainable"],
            "trainable_purpose": rules["trainable_purpose"],
            "refused": rules["refused"],
            "held_out": rules["held_out"],
            "single_use": rules["single_use"],
            "fitting": rules["fitting"],
            "quarantine_bucket": rules["quarantine_bucket"],
            "partitions": rules["roles"],
            "grouping": rules["grouping"],
            "assignment": rules["assignment"],
            "owner": rules["owner"],
            "enforcement": rules["enforcement"],
            "exclusion_codes": list(exclusion_codes()),
        },
        "source_manifest": wf.manifest_ref(eval_manifest),
        # The owner's OWN digest of the exact item set this export drew from, taken over the
        # partition name and its members and deliberately not over the manifest id -- so a later
        # reader can say which of the two moved. Recording it here is reuse, not a second identity:
        # `workflow_eval.partition_digest` is the one function that computes it.
        "source_partition_digest": wf.partition_digest(eval_manifest, partition),
        "schemas": {
            "snapshot": SNAPSHOT_VERSION,
            "taxonomy": TAXONOMY_VERSION,
            "lifecycle": LIFECYCLE_VERSION,
            "dataset": DATASET_VERSION,
            "contract": _contract().CONTRACT_VERSION,
            "eval_manifest": wf.MANIFEST_VERSION,
            "payload_fields": list(PAYLOAD_FIELDS),
            "payload_entry_keys": list(PAYLOAD_ENTRY_KEYS),
            "audit_fields": list(AUDIT_FIELDS),
            "shared_fields": sorted(set(PAYLOAD_FIELDS) & set(AUDIT_FIELDS)),
        },
        "eligibility": {
            "declared_purpose": purpose,
            "destination": destination,
            "checked_at": checked_at,
            "gate": "training_data.export_eligibility",
            "note": "the gate DECIDES and this export ACTS on its decision: a record with a "
                    "non-empty refusal list never reaches a payload line",
        },
        "exposure": {
            "checked": exposure is not None,
            "store": "caller-supplied" if exposure_dir is not None else None,
            "entries": None if exposure is None else exposure["entries"],
            "unreadable": None if exposure is None else exposure["unreadable"],
            "owner": "bin/workflow_eval.py:exposure_state",
            "recorded_here": False,
        },
        "examples": examples,
        "groups": {gid: groups[gid] for gid in sorted(groups)},
        "counts": {
            "offered": offered,
            "unique": len(unique),
            "duplicates_collapsed": duplicates,
            "included": len(examples),
            "excluded": len(excluded),
            "groups": len(groups),
            "items": len(drawn_items),
        },
        # Already in example-id order: the loop above iterates `sorted(unique)`, which is the
        # ONE place ordering is decided. A second sort here would be a copy of that decision,
        # and a copy that cannot be shown to be load-bearing is not a guard.
        "excluded": excluded,
        "excluded_by_code": dict(sorted(by_code.items())),
        "excluded_by_label_status": dict(sorted(by_status.items())),
        "included_by_target": dict(sorted(by_target.items())),
        "content_identities": {
            "payload_sha": hashlib.sha256(payload_blob).hexdigest(),
            "audit_metadata_sha": hashlib.sha256(audit_blob).hexdigest(),
            "payload_lines": len(payload_lines),
            "audit_metadata_lines": len(audit_lines),
            "payload_bytes": len(payload_blob),
            "audit_metadata_bytes": len(audit_blob),
        },
        "not_established": list(DATASET_NOT_ESTABLISHED),
        "not_established_notes": dict(sorted(DATASET_NOT_ESTABLISHED_NOTES.items())),
        "notes": [AUDIT_SEPARATION_NOTE, DETERMINISM_NOTE, GROUPING_UNCERTAINTY_NOTE,
                  REDACTION_LIMIT_NOTE, LABEL_SEPARATE_NOTE, NOT_WIRED_LABEL],
    }
    sha = _sha(content)
    manifest = {
        "v": DATASET_VERSION,
        "dataset_id": _dataset_id(f"ds-{sha[:16]}"),
        "sha": sha,
        "digest": {
            "algorithm": "sha256",
            "canonical": "bin/decision_contract.py:dumps",
            "over": "content",
            "excludes": ["built_at", "built_by", "dataset_id", "sha", "digest"],
            "note": DATASET_NOT_ESTABLISHED_NOTES["digest-identifies-content-not-provenance"],
        },
        "built_at": built,
        "built_by": author,
        "content": content,
    }
    return {
        "manifest": manifest,
        "payload": payload_lines,
        "audit_metadata": audit_lines,
        "bytes": {
            "payload": payload_blob,
            "audit_metadata": audit_blob,
            "manifest": (canonical(manifest) + "\n").encode("utf-8"),
        },
    }


def dataset_integrity(manifest):
    """Recompute an export's identity -> `{"sha_ok", "id_ok", "recomputed"}`.

    A digest IDENTIFIES content; it is not protection against a worker that can rewrite the file.
    See `DATASET_NOT_ESTABLISHED_NOTES['digest-identifies-content-not-provenance']`.
    """
    if not isinstance(manifest, Mapping) or manifest.get("v") != DATASET_VERSION:
        raise _refuse("not-a-reference", f"this is not a {DATASET_VERSION} export")
    sha = _sha(manifest.get("content"))
    return {"sha_ok": sha == manifest.get("sha"),
            "id_ok": manifest.get("dataset_id") == f"ds-{sha[:16]}",
            "recomputed": sha}


# ---- dataset persistence, through the same store seam -------------------------------------------

def write_dataset(dataset, store_dir):
    """Write one export -> `{"written", "path", "dataset_id", "reason"}`. Create-once.

    IMMUTABLE BY CONSTRUCTION. All three files go through `safe_paths.confined_create_bytes`, whose
    `O_EXCL` makes "is this name free" and the write one kernel operation and treats a symlink at
    the leaf as taken rather than followed. Nothing here overwrites an export.

    RE-EXPORTING THE SAME MATERIAL IS A NO-OP THAT KEEPS THE FIRST, so the `built_at` on disk stays
    the real one. The comparison is over `content`, which excludes provenance: the same records
    exported again tomorrow are the same dataset. Different content under the same id is refused
    loudly -- with a content-addressed id that means a rewrite or a sha256 collision, not a re-run.

    The manifest is written LAST, so its presence implies the two files whose digests it carries.
    """
    manifest = dataset["manifest"]
    report = dataset_integrity(manifest)
    broken = sorted(name for name, ok in report.items() if name.endswith("_ok") and not ok)
    if broken:
        raise _refuse("value-invalid",
                      f"the export fails {', '.join(broken)}: its content has moved since it was "
                      f"built, so it is not the dataset it claims to be")
    did = _dataset_id(manifest["dataset_id"])
    sp = _sp()
    root = Path(store_dir)
    rel = {name: f"{DATASET_DIR}/{did}/{DATASET_FILES[name]}" for name in DATASET_FILES}
    held = (sp.confined_read_bytes(root, rel["manifest"], what="training dataset manifest",
                                   missing_ok=True) if root.is_dir() else None)
    if held:
        stored = _contract().loads(held.decode("utf-8"))
        if not isinstance(stored, Mapping) or stored.get("v") != DATASET_VERSION:
            raise _refuse("unknown-value",
                          f"{rel['manifest']} is stamped {(stored or {}).get('v')!r}; this writer "
                          f"writes {DATASET_VERSION!r}")
        if canonical(stored.get("content")) != canonical(manifest["content"]):
            raise _refuse(
                "duplicate-entry",
                f"{did} already exists with DIFFERENT content: a dataset id is the digest of the "
                f"content it names, so this is a rewrite (or a sha256 collision), not a re-export. "
                f"Nothing was overwritten")
        return {"written": False, "path": str(root / rel["manifest"]), "dataset_id": did,
                "reason": "already-exported"}
    _rt().ensure_private(root)
    for name in ("payload", "audit_metadata", "manifest"):
        data = dataset["bytes"][name]
        try:
            sp.confined_create_bytes(root, rel[name], data, what=f"training dataset {name}")
        except sp.SafePathExists:
            on_disk = sp.confined_read_bytes(root, rel[name], what=f"training dataset {name}")
            if on_disk != data:
                raise _refuse(
                    "duplicate-entry",
                    f"{rel[name]} already holds different bytes under a content-addressed id. An "
                    f"export is immutable, so nothing was overwritten") from None
    return {"written": True, "path": str(root / rel["manifest"]), "dataset_id": did,
            "reason": None}


def read_dataset(store_dir, dataset_id):
    """Load one export and re-derive every identity it claims -> `{manifest, payload, audit}`.

    Four checks, and together they are the chain of custody such as it is: the manifest's `content`
    must still digest to its `sha`; that sha's prefix must still be the id it is FILED under; and
    each data file must still digest to the `content_identities` row the manifest carries. A
    tamperer who recomputes the manifest digest changes the id and therefore the directory name, and
    every reference to it stops resolving. That is DETECTION, never prevention.

    A store that does not exist holds nothing, and reading never creates it -- only a write does.
    """
    sp = _sp()
    root = Path(store_dir)
    did = _dataset_id(dataset_id)
    rel = {name: f"{DATASET_DIR}/{did}/{DATASET_FILES[name]}" for name in DATASET_FILES}
    raw = (sp.confined_read_bytes(root, rel["manifest"], what="training dataset manifest",
                                  missing_ok=True) if root.is_dir() else None)
    if not raw:
        raise _refuse("not-a-reference", f"no dataset {did!r} under {store_dir}")
    manifest = _contract().loads(raw.decode("utf-8"))
    if not isinstance(manifest, Mapping) or manifest.get("v") != DATASET_VERSION:
        raise _refuse("unknown-value",
                      f"{rel['manifest']} is stamped {(manifest or {}).get('v')!r}; this reader "
                      f"reads {DATASET_VERSION!r}")
    report = dataset_integrity(manifest)
    broken = sorted(name for name, ok in report.items() if name.endswith("_ok") and not ok)
    if broken:
        raise _refuse("value-invalid",
                      f"{did} fails {', '.join(broken)}: its content has been rewritten since it "
                      f"was exported, so it is not the dataset it claims to be")
    identities = manifest["content"]["content_identities"]
    out = {"manifest": manifest}
    for name, count in (("payload", "payload_lines"),
                        ("audit_metadata", "audit_metadata_lines")):
        blob = sp.confined_read_bytes(root, rel[name], what=f"training dataset {name}",
                                      missing_ok=True) or b""
        if hashlib.sha256(blob).hexdigest() != identities[f"{name}_sha"]:
            raise _refuse("value-invalid",
                          f"{rel[name]} does not match the digest the manifest carries for it: the "
                          f"file has moved since it was exported")
        # No line-count check: the digest above already establishes that these are exactly the
        # bytes that were exported, and the manifest's count was computed from those same lines. A
        # count that could not disagree is not a guard, so `{count}` is read as metadata only.
        out[name] = [_contract().loads(line) for line in blob.decode("utf-8").splitlines()
                     if line.strip()]
        out[f"{name}_lines_declared"] = identities[count]
    return out


# ---- the opt-in hook ----------------------------------------------------------------------------

def capture_hook(build, *, store_dir=None, scope=None, enabled=None):
    """The seam a decision or attempt owner would call -> a report. NEVER raises.

    WITH COLLECTION OFF IT DOES NOTHING AT ALL. `build` is a callable rather than a payload
    precisely so that this is true: the evidence is not gathered, no artifact is read, no digest
    is taken, no directory is created and no path is touched. The host's own behaviour is
    therefore byte-identical to a host with no hook in it, which is what "disabled collection
    preserves legacy behaviour" has to mean to be worth asserting.

    IT NEVER RAISES, on purpose. A capture is an observation of a run, and an observation that
    can break the run it observes is worse than no observation. A refusal -- an ineligible
    scope, oversize evidence, a fact from after the decision -- comes back as `collected: False`
    with its reason and the refusal's own message, and nothing is written either way. The strict
    form is `snapshot()`, which raises, and that is what tests and an operator's own tooling
    should call directly.

    NOTHING CALLS THIS. `CAPTURE_WIRED` is False.
    """
    built = False
    try:
        state = collection_state(scope=scope, enabled=enabled)
        if not state["collecting"]:
            return {"collected": False, "reason": state["reason"], "error": None,
                    "receipt": None, "built": False, "wired": bool(CAPTURE_WIRED),
                    "note": state["note"]}
        if store_dir is None:
            raise _refuse("missing-field",
                          "no store directory was given; a capture writes through the store "
                          "seam, never to a path this module chose for itself")
        built = True
        kwargs = build()
        if not isinstance(kwargs, Mapping):
            raise _refuse("wrong-type",
                          f"the build callable must return the keyword arguments for "
                          f"snapshot(), got {type(kwargs).__name__}")
        record = snapshot(scope=scope, **dict(kwargs))
        receipt = persist(record, store_dir)
    except Exception as exc:  # noqa: BLE001 -- see the docstring: this hook never raises
        # The state check is INSIDE the try as well: a caller who passed something that is not
        # a CollectionScope gets a refusal like any other, because "never raises" that holds
        # only for well-formed arguments is not a promise a host can rely on.
        return {"collected": False, "reason": "refused", "built": built, "error": str(exc),
                "receipt": None, "wired": bool(CAPTURE_WIRED), "note": None}
    return {"collected": True, "reason": None, "built": True, "error": None,
            "receipt": receipt, "wired": bool(CAPTURE_WIRED), "note": None}


def status(repo_root=None, env=None):
    """What an operator needs to know before trusting either answer -> a report.

    Both switches are re-derived here, so this is a measurement rather than a memory.
    """
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent
    resolved = _rt().resolve_store(STORE, root, env=env)
    return {
        "v": SNAPSHOT_VERSION,
        "taxonomy_v": TAXONOMY_VERSION,
        "lifecycle_v": LIFECYCLE_VERSION,
        "collection_enabled": bool(COLLECTION_ENABLED),
        "capture_wired": bool(CAPTURE_WIRED),
        "store": STORE,
        "store_path": str(resolved["path"]),
        "store_origin": resolved["origin"],
        "store_exists": Path(resolved["path"]).is_dir(),
        "eligible_to_persist": ELIGIBLE_TO_PERSIST,
        "to_enable": [
            "declare a CollectionScope: purpose, retention_days, owner approval_ref, "
            "eligibility='approved'",
            "pass enabled=True to capture_hook (or set training_data.COLLECTION_ENABLED)",
            "wire capture_hook into a decision or attempt owner -- nothing does today",
        ],
        "notes": [COLLECTION_OFF_LABEL, NOT_WIRED_LABEL, REDACTION_LIMIT_NOTE],
    }


# ---- CLI ------------------------------------------------------------------------------------------

def _demo_scope():
    return collection_scope(
        purpose="demonstrate the capture seam on synthetic fixture data",
        retention_days=30,
        eligibility=ELIGIBLE_TO_PERSIST,
        approval_ref=_al().make_ref("synthetic-approval", version="demo/1"),
        source_restrictions=("synthetic-only",),
    )


def _demo_question():
    return _contract().parse_question({
        "id": "q-missing-contract", "version": "1", "kind": "boolean",
        "question": "Was the failing attempt missing an interface contract it needed?",
        "rubric": {}, "outcomes": ["false", "true"], "abstention": "permitted",
        "dependencies": [], "sensitivity": "project-internal",
    })


def _demo_pool():
    """Three synthetic mined-task records: two variants of one defect, plus a second defect.

    Shaped for `workflow_eval.build_manifest` and invented from nothing -- no repository was read,
    no commit is real, and the two `issue: 1` variants are what make a GROUP rather than two rows.
    """
    def diff(path):
        return (f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n"
                f"@@ -1,1 +1,1 @@\n-    old_call()\n+    new_call()\n")

    return [{"task_id": task_id, "mode": "issue-replay", "issue": issue,
             "base_commit": "0" * 40, "fix_commit": None, "subject": "",
             "statement": f"the adapter drops a record in {task_id}",
             "statement_source": "issue", "reference_patch": diff(f"src/{task_id}.py"),
             "setup_patch": None, "test_blobs": {}, "oracle_tests_available": True,
             "size_profile": "S", "labels": [], "notes": []}
            for task_id, issue in (("D31", 1), ("D31-variant", 1), ("D32", 2))]


def _demo_dataset(record, store, evals):
    """D33's half: place the example in a grouped partition, export, inspect, re-export. Offline.

    The evals directory is a temp sibling of the training store and is only READ: the exposure log
    belongs to `workflow_eval` and this walkthrough writes nothing into it.
    """
    wf = _wf()
    steps = []
    manifest = wf.build_manifest("synthetic://fixture-repo", "0" * 40, _demo_pool(),
                                 allocation={TRAINABLE_PARTITION: 1},
                                 acceptance="python3 run_tests.py",
                                 created_at="2026-09-19T00:00:00+00:00", created_by="demo")
    rules_held_out = dataset_rules()["held_out"]
    group = next(row for row in manifest["content"]["groups"].values() if len(row["items"]) > 1)
    steps.append({"step": "grouped by defect", "groups": len(manifest["content"]["groups"]),
                  "largest_group": group["key"], "variants": len(group["items"]),
                  "partition": group["partition"]})
    common = {"eval_manifest": manifest, "store_dir": store, "exposure_dir": evals,
              "purpose": record["eligibility"]["purpose"],
              "destination": "local-development-partition",
              "built_at": "2026-09-20T10:00:00Z", "built_by": "synthetic-operator"}
    exported = build_dataset([record], now="2026-09-20T09:00:00Z", **common)
    rerun = build_dataset([record], now="2026-09-20T09:00:00Z", **common)
    twice = build_dataset([record, record], now="2026-09-20T09:00:00Z", **common)
    steps.append({"step": "dataset built", "dataset_id": exported["manifest"]["dataset_id"],
                  "included": exported["manifest"]["content"]["counts"]["included"],
                  "deterministic": rerun["bytes"] == exported["bytes"],
                  # The same record offered twice collapses to one payload line. The MANIFEST still
                  # differs, and must: it records that a duplicate was offered and collapsed, which
                  # is a different accounting of the same material.
                  "duplicate_collapsed_to_one_line":
                      twice["bytes"]["payload"] == exported["bytes"]["payload"],
                  "duplicates_collapsed":
                      twice["manifest"]["content"]["counts"]["duplicates_collapsed"]})
    receipt = write_dataset(exported, store)
    rewrite = write_dataset(exported, store)
    inspected = read_dataset(store, exported["manifest"]["dataset_id"])
    steps.append({"step": "dataset written and inspected", "written": receipt["written"],
                  "second_write": rewrite["reason"],
                  "payload_keys": sorted(inspected["payload"][0]),
                  "audit_only": sorted(set(AUDIT_FIELDS) - set(PAYLOAD_FIELDS))[:3]})
    for name in rules_held_out:
        held = wf.build_manifest("synthetic://fixture-repo", "0" * 40, _demo_pool(),
                                 allocation={name: 1}, acceptance="python3 run_tests.py",
                                 created_at="2026-09-19T00:00:00+00:00", created_by="demo")
        refused = build_dataset([record], now="2026-09-20T09:00:00Z",
                                **dict(common, eval_manifest=held))
        steps.append({"step": f"{name} material refused",
                      "included": refused["manifest"]["content"]["counts"]["included"],
                      "refusals": refused["manifest"]["content"]["excluded_by_code"]})
    return steps, common, exported["manifest"]["dataset_id"]


def _demo_lifecycle(record, store, evals):
    """D32's half of the walkthrough: review, correct, export, revoke, refuse. Offline."""
    steps = []
    later = "2026-09-19T12:00:00Z"
    reviewed = _al().make_ref("review-1", version="fixture/1")
    thin = adjudicate(record, shape="failure-cause", cause="missing-context",
                      reviewer={"id": "synthetic-reviewer", "source": "human-adjudication"},
                      decided_at=later, claim={"claimed_cause": "missing-context"},
                      suggestion={"by": _al().make_ref("synthetic-model"),
                                  "claim": {"guessed_cause": "missing-context"}})
    steps.append({"step": "unsupported claim", "status": thin["status"],
                  "cause": thin["cause"], "reason": thin["unresolved_reason"]})
    supported = adjudicate(
        record, shape="failure-cause", cause="missing-context",
        reviewer={"id": "synthetic-reviewer", "source": "human-adjudication"},
        decided_at=later,
        evidence=[review_evidence(source="human-adjudication", ref=reviewed,
                                  observed_at=later, stage="verify")],
        prior=thin, correction_reason="an independent reader looked at the reproduction")
    persist_lifecycle(thin, store)
    persist_lifecycle(supported, store)
    state = label_state(read_lifecycle(store, record["example_id"], "adjudication"))
    steps.append({"step": "reviewed and corrected", "status": state["status"],
                  "corrections": len(state["corrections"]),
                  "target_eligible": state["target"]["eligible"]})
    allowed = export_eligibility(record, now="2026-09-20T09:00:00Z",
                                 purpose=record["eligibility"]["purpose"],
                                 destination="local-development-partition", store_dir=store)
    steps.append({"step": "export decided", "exportable": allowed["exportable"],
                  "refusals": allowed["refusals"]})
    dataset_steps, common, first_id = _demo_dataset(record, store, evals)
    steps.extend(dataset_steps)
    stale = export_eligibility(record, now="2027-09-20T09:00:00Z",
                               purpose=record["eligibility"]["purpose"],
                               destination="local-development-partition", store_dir=store)
    steps.append({"step": "retention expired", "exportable": stale["exportable"],
                  "refusals": stale["refusals"]})
    tombstone = revoke(record, revoked_at="2026-09-21T08:00:00Z",
                       reason="the owner withdrew this example",
                       by=_al().make_ref("synthetic-owner"),
                       dependents=[{"kind": "export-manifest",
                                    "ref": _al().make_ref("manifest-1")},
                                   {"kind": "trained-checkpoint",
                                    "ref": _al().make_ref("checkpoint-1")}])
    persist_lifecycle(tombstone, store)
    steps.append({"step": "revoked", "invalidated": tombstone["invalidated"],
                  "identified": tombstone["identified"],
                  "unreached": tombstone["unreached"]})
    refused = export_eligibility(record, now="2026-09-22T09:00:00Z",
                                 purpose=record["eligibility"]["purpose"],
                                 destination="local-development-partition", store_dir=store)
    steps.append({"step": "re-export refused", "exportable": refused["exportable"],
                  "refusals": refused["refusals"],
                  "unreached": refused["unreached"]})
    withdrawn = build_dataset([record], now="2026-09-22T09:00:00Z", **common)
    steps.append({"step": "revoked example leaves the dataset",
                  "included": withdrawn["manifest"]["content"]["counts"]["included"],
                  "refusals": withdrawn["manifest"]["content"]["excluded_by_code"],
                  "dataset_id_changed":
                      withdrawn["manifest"]["dataset_id"] != first_id})
    return steps


def _demo(as_json=False):
    """The whole seam over synthetic data in a temp dir. Offline; spends nothing."""
    out = {"synthetic": True, "note": SYNTHETIC_NOTE, "steps": [],
           "exposure_log_files": 0}
    predicted = "2026-09-19T10:00:00Z"
    build_kwargs = {
        "question": _demo_question(),
        "prediction_at": predicted,
        "captured_at": "2026-09-19T10:00:05Z",
        "sources": {
            "attempt_ref": _al().make_ref("a1b2c3d4", version=_al().LEDGER_VERSION),
            "task_ref": _al().make_ref("D31"),
        },
        "input": {
            "observed_error": [{"text": "AttributeError: 'Adapter' object has no attribute 'emit'",
                                "observed_at": "2026-09-19T09:59:00Z",
                                "source": "verify-tail", "artifact_sha": None}],
            "task_statement": [{"text": "make the adapter emit a bounded record",
                                "observed_at": "2026-09-19T09:58:00Z",
                                "source": "task-brief", "artifact_sha": None}],
        },
        "boundary": {"sequence": 3, "event": "attempt.failed"},
        "reproducibility": {"harness": "stub", "requested_model": "tier-mid"},
        "operational_class": "unknown",
    }
    disabled = capture_hook(lambda: dict(build_kwargs), store_dir=None, scope=None, enabled=None)
    out["steps"].append({"step": "collection off", "collected": disabled["collected"],
                         "reason": disabled["reason"]})
    base = Path(tempfile.mkdtemp(prefix="training-demo-"))
    temp = base / "training"      # the training store this module owns and writes
    # Named for what it holds rather than for the store, because `bin/workflow_eval.py` is the
    # ONE engine that may resolve the evals store by name and this module must not look like
    # a second one (tests/test_decision_evaluation_manifest.py enforces that).
    exposure = base / "eval-exposure"   # workflow_eval's log, READ here and never written
    try:
        scope = _demo_scope()
        first = capture_hook(lambda: dict(build_kwargs), store_dir=temp, scope=scope,
                             enabled=True)
        again = capture_hook(lambda: dict(build_kwargs), store_dir=temp, scope=scope,
                             enabled=True)
        out["steps"].append({"step": "scoped capture", "collected": first["collected"],
                             "example_id": (first["receipt"] or {}).get("example_id")})
        out["steps"].append({"step": "same evidence again",
                             "written": (again["receipt"] or {}).get("written"),
                             "reason": (again["receipt"] or {}).get("reason")})
        stored = read_snapshots(temp, build_kwargs["captured_at"])
        out["stored"] = len(stored)
        out["unknown"] = stored[0]["unknown"] if stored else []
        leaked = capture_hook(
            lambda: dict(build_kwargs, input={"observed_error": [{
                "text": "token sk-ant-" + "a" * 40 + " rejected",
                "observed_at": "2026-09-19T09:59:30Z", "source": "verify-tail",
                "artifact_sha": None}]}),
            store_dir=temp, scope=scope, enabled=True)
        redacted = (read_snapshots(temp, build_kwargs["captured_at"])[-1]["redaction"]
                    if leaked["collected"] else {})
        out["steps"].append({"step": "credential-shaped text", "collected": leaked["collected"],
                             "redactions": redacted.get("redactions")})
        future = capture_hook(
            lambda: dict(build_kwargs, input={"code_context": [{
                "text": "the patch that fixed it", "observed_at": "2026-09-19T11:00:00Z",
                "source": "later-commit", "artifact_sha": None}]}),
            store_dir=temp, scope=scope, enabled=True)
        out["steps"].append({"step": "evidence from after the decision",
                             "collected": future["collected"], "error": future["error"]})
        unknown_rights = capture_hook(
            lambda: dict(build_kwargs), store_dir=temp, enabled=True,
            scope=collection_scope(purpose="collect with rights nobody has confirmed",
                                   retention_days=30,
                                   approval_ref=_al().make_ref("synthetic-approval")))
        out["steps"].append({"step": "unknown eligibility",
                             "collected": unknown_rights["collected"],
                             "reason": unknown_rights["reason"]})
        if stored:
            pair = attach_label(stored[0], {"claimed_cause": "missing-context",
                                            "by": "synthetic-reviewer"})
            out["steps"].append({
                "step": "late label",
                "example_bytes_unchanged": canonical(pair["example"]) == canonical(stored[0]),
                "label_points_at": pair["label"]["input_sha"][:12],
                "label_status": pair["label"]["status"]})
            out["steps"].extend(_demo_lifecycle(stored[0], temp, exposure))
        out["exposure_log_files"] = (len(list(exposure.rglob("*")))
                                     if exposure.exists() else 0)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    if as_json:
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0
    print(f"synthetic demo — {SYNTHETIC_NOTE}")
    for step in out["steps"]:
        detail = ", ".join(f"{k}={v!r}" for k, v in step.items() if k != "step")
        print(f"  {step['step']:32s} {detail}")
    print(f"  stored records: {out['stored']}")
    print(f"  unknown on the first record: {', '.join(out['unknown'])}")
    print(f"  the evaluation exposure log was read and never written: "
          f"{out['exposure_log_files']} file(s) under it")
    return 0


def _cli(argv=None):
    parser = argparse.ArgumentParser(
        prog="training_data.py",
        description="Decision-time snapshots for a future specialist. Collection is OFF.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for verb, help_text in (("status", "is collection on, where would it write, what is wired"),
                            ("taxonomy", "the cause taxonomy, reconciled against the ledger"),
                            ("demo", "the whole seam over synthetic data in a temp dir")):
        node = sub.add_parser(verb, help=help_text)
        node.add_argument("--json", action="store_true")
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.cmd == "demo":
        return _demo(as_json=args.json)
    payload = status() if args.cmd == "status" else reconcile_operational_classes()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.cmd == "status":
        print(f"collection enabled : {payload['collection_enabled']}")
        print(f"capture wired      : {payload['capture_wired']}")
        print(f"store              : {payload['store_path']} ({payload['store_origin']}, "
              f"exists={payload['store_exists']})")
        for step in payload["to_enable"]:
            print(f"  to enable: {step}")
        for note in payload["notes"]:
            print(f"  — {note}")
        return 0
    print(f"taxonomy {payload['taxonomy_v']}")
    for name in payload["classes"]:
        mark = "review-only" if name in payload["review_only"] else "from-evidence"
        print(f"  {name:28s} {mark}")
    print(f"operational owner: {payload['operational_owner']}")
    for operational, candidate in payload["candidate_of"].items():
        print(f"  {operational:16s} -> {candidate}")
    print(f"  never produced by classify_dispatch: "
          f"{', '.join(payload['not_produced_by_dispatch'])}")
    print(f"  — {payload['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
