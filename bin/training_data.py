#!/usr/bin/env python3
"""D31 -- the evidence ONE decision had in front of it, frozen, and nothing else.

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
example. The label lifecycle itself -- review, correction history, disagreement, adjudicated
targets -- is D32's, and this module deliberately implements none of it: `status` on a label
reference is `unadjudicated` and nothing here can change it.

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
root `bin/runtime_data.py` resolved. It is not an exporter and it is not a trainer: local JSONL
datasets and manifests are D33's, readiness is D34's, and no code path here reaches a network,
a provider, a model or a real harness home.
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

    IT REFUSES WHAT IT CANNOT WALK, AND WHAT IS NOT JSON. A walker handed a container it does
    not descend into inspects nothing and certifies everything, so bytes, a set, a view, a
    generator and any other object are refusals rather than passes. A namedtuple is refused
    although it IS a tuple, because walking it as one would inspect its values and never its
    field names -- which is where an input-shaped key would be hiding.

    WHAT IT DOES NOT PROVE. This matches KEY spellings. A label that writes the task statement
    into a VALUE under an innocent key is not caught here -- what stops that one is the
    separation of artifacts: the example's bytes are digested and never rewritten, so whatever a
    label says, the input it points at is still the input.
    """
    hits = []
    unwalkable = []
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, Mapping):
            for key, sub in item.items():
                if _is_input_shaped(key):
                    hits.append(key)
                stack.append(sub)
        elif isinstance(item, (str, int, float, type(None))):
            continue  # the JSON scalars; `bool` is an `int` and arrives here
        elif hasattr(item, "_fields"):
            unwalkable.append(type(item).__name__)  # a namedtuple: values walked, names lost
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
        else:
            unwalkable.append(type(item).__name__)
    if hits:
        raise _refuse(
            "authority-field",
            f"{where} carries {', '.join(repr(h) for h in sorted(set(hits)))}, which is "
            f"input-time evidence. {LABEL_SEPARATE_NOTE}")
    if unwalkable:
        raise _refuse(
            "authority-field",
            f"{where} carries a value this sweep cannot inspect: "
            f"{', '.join(sorted(set(unwalkable)))}. A container that is not walked is not "
            f"checked, so it is refused rather than passed over")
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

    IT IS NOT THE LABEL LIFECYCLE. D32 owns review, correction history, disagreement and
    adjudicated targets. What comes out of here is `status: "unadjudicated"` with the payload
    quoted verbatim under `claim`, and nothing in this module can advance it -- a provider's or
    a reviewer's opinion is a candidate, never independently verified truth.
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


def _demo(as_json=False):
    """The whole seam over synthetic data in a temp dir. Offline; spends nothing."""
    out = {"synthetic": True, "note": SYNTHETIC_NOTE, "steps": []}
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
    temp = Path(tempfile.mkdtemp(prefix="training-demo-"))
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
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    if as_json:
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0
    print(f"synthetic demo — {SYNTHETIC_NOTE}")
    for step in out["steps"]:
        detail = ", ".join(f"{k}={v!r}" for k, v in step.items() if k != "step")
        print(f"  {step['step']:32s} {detail}")
    print(f"  stored records: {out['stored']}")
    print(f"  unknown on the first record: {', '.join(out['unknown'])}")
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
