#!/usr/bin/env python3
"""D09 -- the strict contract for a decision: what may be asked, answered, and recorded.

Four objects live here, in the shapes the shared plan
(`tasks/kits/decision-improvement/PLAN.md`, "Data contracts and fixed authority") pins:

  * `QuestionSpec`    -- a stable, versioned question WITH its complete wording and rubric.
  * `DecisionRequest` -- what a coordinator asks, and the exact world it asks it about.
  * `DecisionResult`  -- what a provider answered, checked back against that exact world.
  * `DecisionRecord`  -- what the coordinator then DID, which the coordinator alone composes.

THIS MODULE IS A LIBRARY, NOT AN ENGINE. It starts no process, opens no store, reads no home
directory and has no CLI, so there is nothing here to run `--demo` against. Its callers are the
engines: D12's provider, D13's policy selection, and whatever coordinator wires them.

============================================================================================
 WHAT VALIDATION HERE DOES AND DOES NOT PROVE
============================================================================================
A payload that parses is WELL FORMED and CONSISTENT WITH ITS REQUEST. That is all. It is not
evidence that the answer is true, that the provider was competent, that the state it describes
still holds, or that anything may now be done. In the plan's words: a provider cannot execute
tools, grant permission, raise a budget, modify the DAG, remove mandatory review, accept an
artifact, alter controller logic or approve a candidate -- so none of those can be expressed
here at all. `BANNED_FIELDS` is that rule made mechanical: any key that reduces to one of those
names -- letters and digits only, case and punctuation discarded, checked on the whole key AND
on each period-delimited component of it -- is refused wherever it appears, in any object,
before anything else is looked at. `_is_banned_key` is that comparison and says exactly what it
does not cover; in particular the reduction is ASCII-shaped, not a unicode normalisation, so a
homoglyph spelling of a banned name is NOT caught by it.

The same holds for identity. A `sha` in this module IDENTIFIES content and DETECTS change; it
prevents nothing. Anything running with the user's own privileges can rewrite a payload and
recompute its digest. What the digests buy is that a result cannot be silently matched to a
DIFFERENT question set or a DIFFERENT state snapshot than the one that was asked about.

============================================================================================
 THE FOUR DESIGN CHOICES WORTH ARGUING WITH
============================================================================================
1. EVERY KEY IS REQUIRED; UNKNOWN IS AN EXPLICIT `null`. There are no optional keys. A provider
   that does not know which model served the call writes `"observed_model": null`, and a
   coordinator reading it sees a disclosed unknown rather than a key someone forgot. The cost
   is verbose payloads; the benefit is that "absent" can never masquerade as "not applicable".
   Adding a field later is therefore a `CONTRACT_VERSION` bump, which is what the constant is
   for. D10's numeric slots (`raw`, `calibrated`, `vendor_confidence`) are declared HERE, empty,
   for exactly this reason -- the same precedent `attempt_history.DURATION_BASES` set by
   reserving `decision-latency` before anything produced it.

2. A RECORD CANNOT BE PARSED WITHOUT ITS REQUEST AND RESULT. There is deliberately no
   context-free record parser. `build_record` takes the coordinator's own decisions as
   keyword-only arguments and `parse_record` demands the request and result it closes over, so
   a provider payload alone can never become a record no matter what it contains. That is the
   mechanical form of "DecisionRecord construction stays coordinator-owned".

3. IDENTITY CHECKS APPLY TO TERMINAL STATUSES TOO. `unsupported`, `unavailable`, `invalid` and
   `timeout` carry no values, but they still have to be answers to THIS request: a timeout
   correlated to another request is not this request's timeout, and accepting it would let a
   stale or replayed failure close a live call.

4. NOTHING HERE OWNS A VERSION IT DID NOT DEFINE. A provenance reference is
   `attempt_ledger.make_ref`'s shape and is built by it, an operation scope is a key of
   `kit_contract.OPERATION_CAPS`, a duration is `attempt_history._duration` on the basis that
   module already reserved, and a resource basis is one of its `COST_BASES`. The version a
   `decision_ref` carries is `CONTRACT_VERSION` -- this object's -- never the ledger's, which
   versions the event line rather than what the line points at.
"""

import dataclasses
import hashlib
import importlib.util
import json
import math
import re
import types
from pathlib import Path

#: The contract version of the four objects below, together. They change together -- a request
#: shape that a result cannot answer is not a separate contract -- so they share one constant
#: rather than four release-surface rows that would always move in lockstep. Registered in
#: `release_gate.VERSION_SOURCES`, which is where a reader finds every contract's current
#: version without reading the code. THIS is the version a `decision_ref` carries.
CONTRACT_VERSION = "polytropos.decision/1"

# ---- vocabularies ------------------------------------------------------------------------------

#: What kind of thing a question asks. `boolean` is a single predicate; `choice` is an unordered
#: set of categories; `ordinal` is an ORDERED set of levels, whose order is the order its
#: `outcomes` are listed in, low to high. Independent coexisting hypotheses are separate boolean
#: questions -- never one forced categorical -- because a categorical asserts exclusivity the
#: hypotheses do not have.
QUESTION_KINDS = ("boolean", "choice", "ordinal")

#: A boolean's outcomes are fixed and ordered false -> true, so no two boolean questions can
#: spell their own outcomes differently and quietly become incomparable.
BOOLEAN_OUTCOMES = ("false", "true")

#: Whether a question may be answered with an abstention inside an `ok` result. `forbidden`
#: means the answer is REQUIRED: an `ok` result that abstains on it, or omits it, is refused.
#: It does not oblige a provider to answer -- a provider with nothing to say returns status
#: `abstain` for the whole result, which carries no values at all.
ABSTENTION = ("permitted", "forbidden")

#: How far the question's own text and its answer may travel. A question is content: asking it
#: of a vendor discloses it.
SENSITIVITIES = ("public", "project-internal", "restricted")

#: What the answer will be USED for. Every entry is advisory by construction -- there is
#: deliberately no use that means "act", because an answer never authorises an action; a
#: coordinator does, after its own fresh checks. A new use is a considered addition here, not a
#: free-text field a caller can fill with anything.
INTENDED_USES = ("advice", "shadow-comparison", "recovery-selection", "proposal-evidence")

#: Whether the state this request describes may be sent to a vendor at all. There is no
#: `unknown` scope: not having determined eligibility is not a scope, it is a reason not to ask.
PRIVACY_SCOPES = ("project-local", "vendor-eligible")

#: A result's status, exactly as the plan pins it. `ok` and `abstain` are answers; the other
#: four are terminal and carry no values.
RESULT_STATUSES = ("ok", "abstain", "unsupported", "unavailable", "invalid", "timeout")
ANSWERING_STATUSES = ("ok", "abstain")
TERMINAL_STATUSES = ("unsupported", "unavailable", "invalid", "timeout")

#: What a decision record was operating under. `legacy` is the frozen existing behaviour and
#: stays the default everywhere until an explicit, separately gated activation says otherwise.
DECISION_MODES = ("legacy", "shadow", "canary", "active")

#: The duration basis a decision's own latency is recorded on. `attempt_history` reserved this
#: name for this work; producing it through that module's helper is what keeps it from being
#: summed with a process's wall clock, which is a different quantity from a different clock.
DECISION_DURATION_BASIS = "decision-latency"

# ---- what may never be a field name -------------------------------------------------------------

#: Names that would make a payload executable. A decision object carries judgements about the
#: world, never anything a runtime could be tempted to run. `diff` is deliberately ABSENT: D11's
#: candidate proposal carries a bounded, data-only diff and reuses this tuple as its key
#: allowlist, so banning the word here would ban the legitimate field too.
_EXECUTABLE_FIELDS = (
    "argv", "cmd", "code", "command", "entrypoint", "eval", "exec", "hook", "import",
    "module", "patch", "pythonpath", "script", "shell", "subprocess",
)

#: Names that would make a payload an authorisation. Every one of these is a decision some
#: OTHER authority owns -- the budget admission, the permission system, the acceptance
#: criteria, the review requirement, the promotion gate -- and none of them may arrive as
#: advice. A request that pins the ceilings it runs under says so in `resource_policy`, whose
#: keys are named so they cannot be mistaken for a grant, and points at the grant itself
#: through `admission_ref`.
_AUTHORITY_FIELDS = (
    "acceptance_override", "activate", "allow_tools", "allowed_tools", "approval", "approve",
    "approved", "approved_by", "authority", "budget", "grant", "max_dispatches",
    "max_escalations", "max_model_calls", "override", "permission", "permissions", "promote",
    "skip_review", "trusted_host", "waive",
)

BANNED_FIELDS = tuple(sorted(_EXECUTABLE_FIELDS + _AUTHORITY_FIELDS))

# ---- bounds -------------------------------------------------------------------------------------
#
# Every one of these exists so a payload cannot become a channel. A rubric belongs in a question
# spec, a state snapshot belongs in the store that owns the state, and neither belongs inside
# something a provider hands back.

MAX_PAYLOAD_CHARS = 64_000
MAX_ID_CHARS = 200
MAX_TEXT_CHARS = 4_000
MIN_QUESTION_CHARS = 24
MIN_QUESTION_WORDS = 5
MIN_RUBRIC_CHARS = 8
MAX_QUESTIONS = 32
MAX_OUTCOMES = 16
MAX_DEPENDENCIES = 16
MAX_ALTERNATIVES = 32
MAX_STATE_ENTRIES = 64
MAX_STATE_VALUE_CHARS = 2_000
MAX_EVIDENCE_REFS = 32
MAX_REASON_CODES = 16
MAX_PROVIDERS = 16
MAX_DISTRIBUTION_ENTRIES = MAX_OUTCOMES

#: How far a choice/ordinal/boolean distribution's entries may sum from 1 and still be
#: accepted. This covers ONLY floating-point summation error -- the gap between the
#: mathematically exact sum and what IEEE-754 addition of the reported floats actually produces
#: -- never a provider's own rounding of the numbers it reports. A sum outside this band is
#: refused outright; nothing in `_distribution` renormalises it back to 1, because a provider
#: payload this far off is malformed, not merely imprecise.
DISTRIBUTION_SUM_TOLERANCE = 1e-6

_SHA_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z")

# ---- refusals ------------------------------------------------------------------------------------

#: Stable machine-readable reasons a payload was refused. Stable because a caller branches on
#: them and a report counts them; a renamed code silently empties somebody's tally.
#: `value-invalid` is the floor for a value this module can see is wrong on its face (a
#: non-finite number, a malformed digest, a distribution entry outside [0, 1], or a distribution
#: whose entries do not sum to 1 within `DISTRIBUTION_SUM_TOLERANCE`). `category-mismatch` is
#: specifically a distribution whose keys are not EXACTLY its question's own categories -- a
#: partial or invented category, never repaired by filling one in or dropping one. An ambiguous
#: rubric -- two levels worded so a grader cannot tell them apart -- reuses `incomplete-question`
#: rather than adding a fourth code for it, because it is the same defect as the cases already
#: filed there: a question that does not yet say enough to be graded.
REASON_CODES = (
    "authority-field",
    "bounds-exceeded",
    "category-mismatch",
    "correlation-mismatch",
    "duplicate-entry",
    "duplicate-key",
    "incomplete-question",
    "missing-answer",
    "missing-field",
    "not-a-reference",
    "stale-admission",
    "state-mismatch",
    "unknown-action",
    "unknown-field",
    "unknown-question",
    "unknown-value",
    "value-invalid",
    "wrong-type",
)
_REASON_SET = frozenset(REASON_CODES)


class ContractError(ValueError):
    """A payload was refused. `code` is one of `REASON_CODES`; the message says which field."""

    def __init__(self, code, message):
        if code not in _REASON_SET:
            raise ValueError(f"{code!r} is not a declared reason code")
        super().__init__(f"[{code}] {message}")
        self.code = code


# ---- sibling loaders (bin/ is not a package) ------------------------------------------------------

_MODS = {}


def _sibling(name):
    if name not in _MODS:
        path = Path(__file__).resolve().parent / f"{name}.py"
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _MODS[name] = mod
    return _MODS[name]


def _al():
    return _sibling("attempt_ledger")


def _ah():
    return _sibling("attempt_history")


def _kc():
    return _sibling("kit_contract")


# ---- canonical form -------------------------------------------------------------------------------

def _canonical(obj):
    """The one serialisation every digest here is taken over.

    `sort_keys` makes a digest independent of dict construction order; the compact separators
    make it independent of anyone's formatter; `allow_nan=False` means a non-finite number
    cannot be smuggled through a digest as the non-standard `NaN` token.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---- duplicate-key-safe parsing ---------------------------------------------------------------------

def _pairs_hook(pairs):
    """`json` keeps the LAST of two identical keys; this refuses the object instead.

    A duplicate key is how two readers of the same bytes disagree: whichever of
    `{"status": "ok", "status": "invalid"}` a parser keeps, the other party read the other one.
    """
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise ContractError(
                "duplicate-key",
                f"the object repeats the key {key!r}; two readers of these bytes would not "
                f"agree on its value, so the payload is refused rather than resolved",
            )
        seen.add(key)
    return dict(pairs)


def _reject_constant(token):
    raise ContractError(
        "value-invalid",
        f"{token} is not a value this contract accepts; it is not JSON, it cannot be compared, "
        f"summed or digested, and a provider that emitted it did not mean a number",
    )


def loads(text):
    """Parse JSON text strictly: bounded, duplicate-key-safe, and non-finite-free."""
    if not isinstance(text, str):
        raise ContractError("wrong-type", f"a payload is JSON text, got {type(text).__name__}")
    if len(text) > MAX_PAYLOAD_CHARS:
        raise ContractError(
            "bounds-exceeded",
            f"the payload is {len(text)} chars; the limit is {MAX_PAYLOAD_CHARS}. A decision "
            f"object carries identities and judgements, not the material they are about",
        )
    try:
        return json.loads(text, object_pairs_hook=_pairs_hook, parse_constant=_reject_constant)
    except ContractError:
        raise
    except json.JSONDecodeError as exc:
        raise ContractError("value-invalid", f"the payload is not JSON: {exc}") from exc


def dumps(payload):
    """The canonical bytes of a payload -- the same form every digest here is taken over."""
    return _canonical(payload)


# ---- primitive validation ------------------------------------------------------------------------

def _alnum(text):
    """Letters and digits only, lowercased.

    Used to ask "is this the same words with different punctuation?" -- which is how an id
    dressed up as a question, an outcome name dressed up as a rubric, or a banned field name
    with a period stuck on it gets past a check that compares the strings as written.
    """
    return re.sub(r"[^a-z0-9]+", "", text.lower())


#: `BANNED_FIELDS` reduced by the SAME function a candidate key is reduced by. Comparing a
#: reduced key against the unreduced tuple would silently unban every multi-word entry in it --
#: `max_dispatches` reduces to `maxdispatches` and would no longer match its own plain
#: spelling -- so the two sides of the comparison are built here, together, from one source.
_BANNED_ALNUM = frozenset(_alnum(name) for name in BANNED_FIELDS)


def _is_banned_key(key):
    """Is this key one of `BANNED_FIELDS`, however it is punctuated?

    Two reductions, both `_alnum`, because one alone leaves a hole:

      * THE WHOLE KEY, which catches punctuation sprinkled through a name -- `approve.`,
        `__approve__`, `allowed-tools`, `a.p.p.r.o.v.e`. A strip-and-swap that only maps '-'
        to '_' leaves a trailing period intact, and `_ID_RE` admits periods, so `approve.` was
        a one-character bypass on every open map here -- including `_distribution`, whose keys
        are PROVIDER-controlled.
      * EACH PERIOD-DELIMITED COMPONENT, which catches a banned name namespaced behind one.
        `budget.x` reduces, as a whole, to `budgetx`; its first component is `budget`. '.' is
        the one separator `_ID_RE` admits that joins two names rather than two words.

    '_' and '-' are deliberately NOT component separators. They join words WITHIN one name, and
    splitting on them would refuse plainly legitimate snapshot keys -- `exit_code`, `patch_sha`,
    `import_count` -- which is how a ban ends up shrunk instead of fixed.

    Neither reduction is unicode normalisation. A homoglyph spelling -- a Cyrillic look-alike
    substituted for a Latin letter -- reduces to something else entirely and is NOT caught
    here. Closing that would be a different and much larger property than this function has.
    """
    if not isinstance(key, str):
        return False
    if _alnum(key) in _BANNED_ALNUM:
        return True
    return any(_alnum(part) in _BANNED_ALNUM for part in key.split("."))


def _reject_banned(mapping, where):
    hits = sorted({key for key in mapping if _is_banned_key(key)})
    if hits:
        raise ContractError(
            "authority-field",
            f"{where} carries {', '.join(repr(h) for h in hits)}. A decision object states what "
            f"is believed, never what may be run or permitted -- execution, permission, budget, "
            f"acceptance, review and promotion each stay with the authority that owns them",
        )


def _object(value, where):
    if not isinstance(value, dict):
        raise ContractError("wrong-type", f"{where} must be an object, got {type(value).__name__}")
    for key in value:
        if not isinstance(key, str):
            raise ContractError("wrong-type", f"{where} has a non-string key {key!r}")
    _reject_banned(value, where)
    return value


def _closed(value, keys, where):
    """Exactly `keys`, no more and no fewer. Unknown is an explicit null, never an absent key."""
    payload = _object(value, where)
    extra = sorted(set(payload) - set(keys))
    if extra:
        raise ContractError(
            "unknown-field",
            f"{where} has unknown field(s) {', '.join(repr(e) for e in extra)}; this contract is "
            f"closed, and a field nothing validates is a field nothing agrees on",
        )
    missing = sorted(key for key in keys if key not in payload)
    if missing:
        raise ContractError(
            "missing-field",
            f"{where} is missing {', '.join(repr(m) for m in missing)}; every field is present "
            f"in this contract and an unknown one is written as an explicit null",
        )
    return payload


def _label(value, where, *, limit=MAX_ID_CHARS):
    if not isinstance(value, str):
        raise ContractError("wrong-type", f"{where} must be a string, got {type(value).__name__}")
    if not value:
        raise ContractError("value-invalid", f"{where} is empty")
    if len(value) > limit:
        raise ContractError("bounds-exceeded",
                            f"{where} is {len(value)} chars; the limit is {limit}")
    if not _ID_RE.match(value):
        raise ContractError(
            "value-invalid",
            f"{where} is {value!r}; an identifier here starts alphanumeric and uses only "
            f"letters, digits, '.', '_' and '-'",
        )
    return value


def _text(value, where, *, minimum=1, limit=MAX_TEXT_CHARS, incomplete=False):
    if not isinstance(value, str):
        raise ContractError("wrong-type", f"{where} must be a string, got {type(value).__name__}")
    stripped = value.strip()
    if len(stripped) < minimum:
        message = f"{where} is {len(stripped)} chars of text; at least {minimum} are needed"
        if incomplete:
            raise ContractError("incomplete-question", message)
        raise ContractError("value-invalid", message)
    if len(value) > limit:
        raise ContractError("bounds-exceeded",
                            f"{where} is {len(value)} chars; the limit is {limit}")
    return value


def _bool(value, where):
    if not isinstance(value, bool):
        raise ContractError("wrong-type",
                            f"{where} must be true or false, got {type(value).__name__}")
    return value


def _number(value, where, *, minimum=None, above=None):
    if isinstance(value, bool):
        raise ContractError(
            "wrong-type",
            f"{where} is a boolean; a boolean is not a number here, and reading it as 0 or 1 "
            f"would invent a magnitude nobody reported",
        )
    if not isinstance(value, (int, float)):
        raise ContractError("wrong-type", f"{where} must be a number, got {type(value).__name__}")
    if not math.isfinite(value):
        raise ContractError("value-invalid", f"{where} is {value!r}, which is not a finite number")
    if minimum is not None and value < minimum:
        raise ContractError("value-invalid", f"{where} is {value!r}; the minimum is {minimum}")
    if above is not None and value <= above:
        raise ContractError("value-invalid", f"{where} is {value!r}; it must exceed {above}")
    return value


def _integer(value, where, *, minimum=None):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError("wrong-type",
                            f"{where} must be an integer, got {type(value).__name__}")
    if minimum is not None and value < minimum:
        raise ContractError("value-invalid", f"{where} is {value}; the minimum is {minimum}")
    return value


def _one_of(value, allowed, where):
    if value not in allowed:
        raise ContractError(
            "unknown-value",
            f"{where} is {value!r}; the vocabulary is {', '.join(repr(a) for a in allowed)}",
        )
    return value


def _sequence(value, where, *, maximum, minimum=0):
    if not isinstance(value, (list, tuple)):
        raise ContractError("wrong-type", f"{where} must be a list, got {type(value).__name__}")
    if len(value) < minimum:
        raise ContractError("bounds-exceeded",
                            f"{where} has {len(value)} entries; at least {minimum} are needed")
    if len(value) > maximum:
        raise ContractError("bounds-exceeded",
                            f"{where} has {len(value)} entries; the limit is {maximum}")
    return list(value)


def _unique_labels(values, where, *, maximum, minimum=0):
    items = _sequence(values, where, maximum=maximum, minimum=minimum)
    out = []
    for index, item in enumerate(items):
        label = _label(item, f"{where}[{index}]")
        if label in out:
            raise ContractError("duplicate-entry", f"{where} repeats {label!r}")
        out.append(label)
    return tuple(out)


def _ref(value, where, *, optional=False):
    """One provenance reference, in `attempt_ledger`'s shape and checked by its own code.

    The ledger owns what a reference IS, so this re-runs the candidate through `make_ref`
    rather than re-implementing the id/length rules. A required reference that is not a
    reference is REFUSED here, which is where the ledger's own reader differs on purpose: an
    event whose pointer is unreadable records unknown provenance, but a request that cannot
    say which acceptance criteria it is about is not a request.
    """
    if value is None:
        if optional:
            return None
        raise ContractError("not-a-reference", f"{where} is required and is null")
    ledger = _al()
    read = ledger.read_ref(value)
    if read is None:
        raise ContractError(
            "not-a-reference",
            f"{where} must be a reference -- an id, optionally the digest of the bytes it names "
            f"and the referenced contract's own version -- got {value!r}",
        )
    if isinstance(value, dict):
        extra = sorted(set(value) - set(ledger.REF_FIELDS))
        if extra:
            raise ContractError(
                "unknown-field",
                f"{where} has unknown field(s) {', '.join(repr(e) for e in extra)}; a reference "
                f"is {', '.join(ledger.REF_FIELDS)} and nothing else",
            )
    try:
        return ledger.make_ref(read["id"], sha=read["sha"], version=read["v"])
    except ledger.RefError as exc:
        raise ContractError("not-a-reference", f"{where}: {exc}") from exc


def _digest(value, where, *, optional=False):
    if value is None:
        if optional:
            return None
        raise ContractError("value-invalid", f"{where} is required and is null")
    if not isinstance(value, str):
        raise ContractError("wrong-type", f"{where} must be a string, got {type(value).__name__}")
    if not _SHA_RE.match(value):
        raise ContractError("value-invalid",
                            f"{where} is not a lowercase sha256 hex digest: {value!r}")
    return value


def _frozen_map(pairs):
    return types.MappingProxyType(dict(pairs))


# ---- state snapshots ---------------------------------------------------------------------------

def _state(value, where):
    """A bounded, FLAT map of scalars. Nesting is refused, which is the whole defence.

    A decision request describes the world it asks about; it does not carry the world. Flatness
    is not a style preference: an arbitrarily nested payload is where a rubric, a diff, a
    transcript or an instruction would hide, and a recursive scan for those is a guess. A
    snapshot is facts of the shape "this file's digest", "this check's exit code".
    """
    payload = _object(value, where)
    if len(payload) > MAX_STATE_ENTRIES:
        raise ContractError(
            "bounds-exceeded",
            f"{where} has {len(payload)} entries; the limit is {MAX_STATE_ENTRIES}. The store "
            f"that owns the state holds the state; this carries the identities of it",
        )
    out = {}
    for key in sorted(payload):
        _label(key, f"{where} key {key!r}")
        item = payload[key]
        if item is None or isinstance(item, bool):
            out[key] = item
        elif isinstance(item, (int, float)):
            out[key] = _number(item, f"{where}[{key!r}]")
        elif isinstance(item, str):
            out[key] = _text(item, f"{where}[{key!r}]", minimum=0,
                             limit=MAX_STATE_VALUE_CHARS)
        else:
            raise ContractError(
                "wrong-type",
                f"{where}[{key!r}] is {type(item).__name__}; a snapshot entry is a string, "
                f"number, boolean or null -- a nested structure here is a payload, not a fact",
            )
    return out


def state_digest(state):
    """The digest a request must declare for its own snapshot. Compute it the same way here."""
    return _sha(_canonical(_state(state, "state")))


def questions_digest(specs):
    """The digest a request must declare for its own question set, wording and rubrics included.

    Taken over the FULL content of every spec, not over their ids: an id that outlived a
    rewording would otherwise let a result answer a question nobody asked in that form.
    """
    return _sha(_canonical([spec.content() for spec in specs]))


# ---- QuestionSpec --------------------------------------------------------------------------------

_QUESTION_KEYS = ("id", "version", "kind", "question", "rubric", "outcomes", "abstention",
                  "dependencies", "sensitivity")


@dataclasses.dataclass(frozen=True)
class QuestionSpec:
    """A question that can be asked again next year and mean the same thing.

    The id is a HANDLE, never the question. A spec carries the complete wording, and for
    `choice` and `ordinal` a rubric entry for every outcome, because "did the id say `q-flaky`?"
    and "was the same thing asked?" are different questions and only the second one is
    answerable from stored evidence. A boolean's wording states its own predicate, so its
    rubric may be empty -- and if it is given it must still cover exactly `false` and `true`.
    """

    id: str
    version: str
    kind: str
    question: str
    rubric: types.MappingProxyType
    outcomes: tuple
    abstention: str
    dependencies: tuple
    sensitivity: str

    @property
    def qualified_id(self):
        """`id@version` -- the key an answer is filed under, so a reworded question misses."""
        return f"{self.id}@{self.version}"

    def content(self):
        return {
            "id": self.id, "version": self.version, "kind": self.kind,
            "question": self.question, "rubric": dict(self.rubric),
            "outcomes": list(self.outcomes), "abstention": self.abstention,
            "dependencies": list(self.dependencies), "sensitivity": self.sensitivity,
        }

    def to_payload(self):
        return self.content()

    def digest(self):
        return _sha(_canonical(self.content()))


def parse_question(value, where="question"):
    payload = _closed(value, _QUESTION_KEYS, where)
    qid = _label(payload["id"], f"{where}.id")
    version = _label(payload["version"], f"{where}.version")
    kind = _one_of(payload["kind"], QUESTION_KINDS, f"{where}.kind")
    question = _text(payload["question"], f"{where}.question", minimum=MIN_QUESTION_CHARS,
                     incomplete=True)

    if _alnum(question) == _alnum(qid):
        raise ContractError(
            "incomplete-question",
            f"{where}.question restates the id {qid!r}; an id is a handle for a question and "
            f"never a substitute for asking it",
        )
    if len(question.split()) < MIN_QUESTION_WORDS:
        raise ContractError(
            "incomplete-question",
            f"{where}.question is {len(question.split())} words; at least {MIN_QUESTION_WORDS} "
            f"are needed for the wording to be the question rather than a label for one",
        )

    outcomes = _unique_labels(payload["outcomes"], f"{where}.outcomes",
                              maximum=MAX_OUTCOMES, minimum=2)
    if kind == "boolean" and outcomes != BOOLEAN_OUTCOMES:
        raise ContractError(
            "value-invalid",
            f"{where}.outcomes for a boolean question are exactly "
            f"{list(BOOLEAN_OUTCOMES)}, got {list(outcomes)}",
        )

    rubric_in = _object(payload["rubric"], f"{where}.rubric")
    if kind == "boolean" and not rubric_in:
        rubric = {}
    else:
        if set(rubric_in) != set(outcomes):
            raise ContractError(
                "incomplete-question",
                f"{where}.rubric covers {sorted(rubric_in)} but the outcomes are "
                f"{sorted(outcomes)}; a level without a rubric is a level two readers grade "
                f"differently",
            )
        rubric = {}
        # Two levels worded the same -- however differently punctuated or cased -- are not two
        # levels a grader can actually tell apart. `_alnum` is the same reduction
        # `_is_banned_key` uses for the identical reason: comparing the strings AS WRITTEN would
        # let "at least one failing assertion follows" and "AT LEAST ONE FAILING ASSERTION
        # FOLLOWS!!" count as different wording when a grader would read them identically.
        seen_wording = {}
        for outcome in outcomes:
            text = _text(rubric_in[outcome], f"{where}.rubric[{outcome!r}]",
                         minimum=MIN_RUBRIC_CHARS, incomplete=True)
            if _alnum(text) == _alnum(outcome):
                raise ContractError(
                    "incomplete-question",
                    f"{where}.rubric[{outcome!r}] just repeats the outcome name; the rubric is "
                    f"what tells a grader when that outcome applies",
                )
            reduced = _alnum(text)
            if reduced in seen_wording:
                raise ContractError(
                    "incomplete-question",
                    f"{where}.rubric[{outcome!r}] is worded the same as "
                    f"{where}.rubric[{seen_wording[reduced]!r}]; two levels a grader cannot "
                    f"tell apart are not two levels, whatever the outcome list says",
                )
            seen_wording[reduced] = outcome
            rubric[outcome] = text

    abstention = _one_of(payload["abstention"], ABSTENTION, f"{where}.abstention")
    dependencies = _unique_labels(payload["dependencies"], f"{where}.dependencies",
                                  maximum=MAX_DEPENDENCIES)
    if qid in dependencies:
        raise ContractError("value-invalid", f"{where}.dependencies lists its own id {qid!r}")
    sensitivity = _one_of(payload["sensitivity"], SENSITIVITIES, f"{where}.sensitivity")

    return QuestionSpec(id=qid, version=version, kind=kind, question=question,
                        rubric=_frozen_map(rubric), outcomes=outcomes, abstention=abstention,
                        dependencies=dependencies, sensitivity=sensitivity)


# ---- DecisionRequest ------------------------------------------------------------------------------

_ELIGIBILITY_KEYS = ("project", "providers", "privacy")
_RESOURCE_KEYS = ("operation_scope", "call_ceiling", "repair_ceiling")
_REQUEST_KEYS = ("v", "correlation_id", "run", "task", "attempt", "intended_use", "task_ref",
                 "acceptance_ref", "state", "state_sha", "alternatives", "questions",
                 "questions_sha", "eligibility", "deadline_s", "resource_policy",
                 "admission_ref")


@dataclasses.dataclass(frozen=True)
class DecisionRequest:
    """What was asked, of whom, about exactly which world, under which already-granted budget."""

    v: str
    correlation_id: str
    run: str
    task: str
    attempt: object
    intended_use: str
    task_ref: types.MappingProxyType
    acceptance_ref: types.MappingProxyType
    state: types.MappingProxyType
    state_sha: str
    alternatives: tuple
    questions: tuple
    questions_sha: str
    eligibility: types.MappingProxyType
    deadline_s: object
    resource_policy: types.MappingProxyType
    admission_ref: types.MappingProxyType

    def question_by_qualified_id(self):
        return {spec.qualified_id: spec for spec in self.questions}

    def to_payload(self):
        return {
            "v": self.v, "correlation_id": self.correlation_id, "run": self.run,
            "task": self.task, "attempt": self.attempt, "intended_use": self.intended_use,
            "task_ref": dict(self.task_ref), "acceptance_ref": dict(self.acceptance_ref),
            "state": dict(self.state), "state_sha": self.state_sha,
            "alternatives": list(self.alternatives),
            "questions": [spec.to_payload() for spec in self.questions],
            "questions_sha": self.questions_sha,
            "eligibility": {"project": self.eligibility["project"],
                            "providers": list(self.eligibility["providers"]),
                            "privacy": self.eligibility["privacy"]},
            "deadline_s": self.deadline_s,
            "resource_policy": dict(self.resource_policy),
            "admission_ref": dict(self.admission_ref),
        }

    def sha(self):
        return _sha(_canonical(self.to_payload()))


def _eligibility(value, where):
    payload = _closed(value, _ELIGIBILITY_KEYS, where)
    project = _label(payload["project"], f"{where}.project")
    providers = _unique_labels(payload["providers"], f"{where}.providers",
                               maximum=MAX_PROVIDERS, minimum=1)
    privacy = _one_of(payload["privacy"], PRIVACY_SCOPES, f"{where}.privacy")
    return _frozen_map({"project": project, "providers": providers, "privacy": privacy})


def _resource_policy(value, where):
    """The ceilings this call already runs under. It grants none of them.

    `operation_scope` is a key of `kit_contract.OPERATION_CAPS`, not a new word: a decision call
    is charged to a scope that already exists and already rolls up into the aggregate cap, so
    nothing here redefines what `max-dispatches` has always counted. The ceilings are a COPY of
    what the admission in `admission_ref` granted, carried so a reader of the request alone can
    see them; re-admission before acting is the coordinator's job and this is not it.
    """
    payload = _closed(value, _RESOURCE_KEYS, where)
    scopes = tuple(_kc().OPERATION_CAPS)
    scope = _one_of(payload["operation_scope"], scopes, f"{where}.operation_scope")
    ceiling = _integer(payload["call_ceiling"], f"{where}.call_ceiling", minimum=1)
    repairs = _integer(payload["repair_ceiling"], f"{where}.repair_ceiling", minimum=0)
    return _frozen_map({"operation_scope": scope, "call_ceiling": ceiling,
                        "repair_ceiling": repairs})


def parse_request(value, where="request"):
    payload = _closed(value, _REQUEST_KEYS, where)
    if payload["v"] != CONTRACT_VERSION:
        raise ContractError(
            "unknown-value",
            f"{where}.v is {payload['v']!r}; this parser reads {CONTRACT_VERSION} and refuses "
            f"to guess at another shape's field meanings",
        )
    correlation_id = _label(payload["correlation_id"], f"{where}.correlation_id")
    run = _label(payload["run"], f"{where}.run")
    task = _label(payload["task"], f"{where}.task")
    attempt = None if payload["attempt"] is None else _label(payload["attempt"],
                                                             f"{where}.attempt")
    intended_use = _one_of(payload["intended_use"], INTENDED_USES, f"{where}.intended_use")
    task_ref = _ref(payload["task_ref"], f"{where}.task_ref")
    acceptance_ref = _ref(payload["acceptance_ref"], f"{where}.acceptance_ref")
    admission_ref = _ref(payload["admission_ref"], f"{where}.admission_ref")

    state = _state(payload["state"], f"{where}.state")
    declared_state = _digest(payload["state_sha"], f"{where}.state_sha")
    actual_state = _sha(_canonical(state))
    if declared_state != actual_state:
        raise ContractError(
            "state-mismatch",
            f"{where}.state_sha says {declared_state} but the snapshot in this payload digests "
            f"to {actual_state}; one of the two is stale and nothing here can tell which",
        )

    alternatives = _unique_labels(payload["alternatives"], f"{where}.alternatives",
                                  maximum=MAX_ALTERNATIVES, minimum=1)

    raw_questions = _sequence(payload["questions"], f"{where}.questions",
                              maximum=MAX_QUESTIONS, minimum=1)
    specs = []
    seen = set()
    for index, item in enumerate(raw_questions):
        spec = parse_question(item, f"{where}.questions[{index}]")
        if spec.qualified_id in seen:
            raise ContractError("duplicate-entry",
                                f"{where}.questions repeats {spec.qualified_id!r}")
        seen.add(spec.qualified_id)
        specs.append(spec)
    for spec in specs:
        for dependency in spec.dependencies:
            if dependency not in {other.id for other in specs}:
                raise ContractError(
                    "unknown-question",
                    f"{where}.questions[{spec.qualified_id!r}] depends on {dependency!r}, which "
                    f"this request does not ask",
                )

    declared_questions = _digest(payload["questions_sha"], f"{where}.questions_sha")
    actual_questions = questions_digest(specs)
    if declared_questions != actual_questions:
        raise ContractError(
            "state-mismatch",
            f"{where}.questions_sha says {declared_questions} but the question set in this "
            f"payload digests to {actual_questions}; the wording and the pin disagree",
        )

    eligibility = _eligibility(payload["eligibility"], f"{where}.eligibility")
    deadline = (None if payload["deadline_s"] is None
                else _number(payload["deadline_s"], f"{where}.deadline_s", above=0))
    resource_policy = _resource_policy(payload["resource_policy"], f"{where}.resource_policy")

    return DecisionRequest(
        v=CONTRACT_VERSION, correlation_id=correlation_id, run=run, task=task, attempt=attempt,
        intended_use=intended_use, task_ref=_frozen_map(task_ref),
        acceptance_ref=_frozen_map(acceptance_ref), state=_frozen_map(state),
        state_sha=declared_state, alternatives=alternatives, questions=tuple(specs),
        questions_sha=declared_questions, eligibility=eligibility, deadline_s=deadline,
        resource_policy=resource_policy, admission_ref=_frozen_map(admission_ref),
    )


# ---- DecisionResult --------------------------------------------------------------------------------

_ANSWER_KEYS = ("outcome", "abstained", "raw", "calibrated", "vendor_confidence")
_RESULT_KEYS = ("v", "correlation_id", "state_sha", "questions_sha", "status", "answers",
                "recommended", "evidence_refs", "requested_provider", "dispatched_provider",
                "observed_provider", "requested_model", "dispatched_model", "observed_model",
                "provider_contract_v", "duration", "usage", "note")


@dataclasses.dataclass(frozen=True)
class DecisionResult:
    """What a provider answered, checked back against the exact request it answers.

    The three provider slots and three model slots are kept apart on purpose: what was asked
    for, what was dispatched, and what was independently observed to have served the call are
    three different facts, and collapsing them is how a pin starts standing in for evidence.
    Any of them may be null, which reads as unknown and never as "the same as the one above".
    """

    v: str
    correlation_id: str
    state_sha: str
    questions_sha: str
    status: str
    answers: types.MappingProxyType
    recommended: object
    evidence_refs: tuple
    requested_provider: object
    dispatched_provider: object
    observed_provider: object
    requested_model: object
    dispatched_model: object
    observed_model: object
    provider_contract_v: object
    duration: object
    usage: object
    note: object

    def to_payload(self):
        return {
            "v": self.v, "correlation_id": self.correlation_id, "state_sha": self.state_sha,
            "questions_sha": self.questions_sha, "status": self.status,
            "answers": {key: dict(value) for key, value in self.answers.items()},
            "recommended": self.recommended,
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "requested_provider": self.requested_provider,
            "dispatched_provider": self.dispatched_provider,
            "observed_provider": self.observed_provider,
            "requested_model": self.requested_model,
            "dispatched_model": self.dispatched_model,
            "observed_model": self.observed_model,
            "provider_contract_v": self.provider_contract_v,
            "duration": None if self.duration is None else dict(self.duration),
            "usage": None if self.usage is None else dict(self.usage),
            "note": self.note,
        }

    def sha(self):
        return _sha(_canonical(self.to_payload()))


def _probability(value, where):
    """One distribution entry: a finite, non-boolean number in the closed interval [0, 1].

    A distribution entry IS a probability, not an arbitrary magnitude -- unlike
    `vendor_confidence`, which stays deliberately unbounded in `_answer` because a vendor's own
    score is not itself a probability of task success. Keeping the two on separate rules is the
    whole point of keeping them as separate fields; this function is what makes the
    `raw`/`calibrated` side of that separation actually enforce its bound.
    """
    number = _number(value, where, minimum=0)
    if number > 1:
        raise ContractError(
            "value-invalid",
            f"{where} is {number!r}; a distribution entry is a probability and cannot exceed 1",
        )
    return number


def _distribution(value, where, *, outcomes):
    """A choice/ordinal/boolean answer's full distribution, checked against its OWN question.

    D09 covered the shape: a bounded map of finite, non-boolean numbers. This is the value
    semantics above that floor, and every one of them fails the same way -- refused, never
    repaired into validity:

      * COVERAGE. The map's keys are EXACTLY `outcomes`, the answering question's own category
        set -- no invented category, and no omitted one. A partial map is not "the rest is
        implied"; it is incomplete. An extra key is not "additional detail"; it is a category
        this question never defined. Both are `category-mismatch`.
      * RANGE. Every entry is a probability in [0, 1] via `_probability`, which also carries
        D09's finite/non-boolean check, so a NaN, an infinity or a bare `true`/`false` is
        refused on the same terms as an entry of 7.
      * SUM. The total is 1 within `DISTRIBUTION_SUM_TOLERANCE` (documented above); a sum
        outside that band is refused rather than silently renormalised back to 1.

    `outcomes` is always the answering `QuestionSpec.outcomes`, so a boolean's own raw
    distribution is held to exactly `{"false", "true"}` on the same terms as a choice or an
    ordinal's map. That is also what keeps coexisting causes apart: they are modelled as
    separate boolean questions precisely so each keeps its own independent distribution here,
    and this function never reads a second question's answer -- two coexisting-cause booleans
    can each report "true" with high probability without their numbers being combined,
    multiplied, or checked against one another.
    """
    if value is None:
        return None
    payload = _object(value, where)
    if len(payload) > MAX_DISTRIBUTION_ENTRIES:
        raise ContractError("bounds-exceeded",
                            f"{where} has {len(payload)} entries; the limit is "
                            f"{MAX_DISTRIBUTION_ENTRIES}")
    if set(payload) != set(outcomes):
        raise ContractError(
            "category-mismatch",
            f"{where} covers {sorted(payload)} but the question's categories are "
            f"{sorted(outcomes)}; a partial or invented category is refused rather than "
            f"filled in or dropped",
        )
    out = {}
    total = 0.0
    for key in sorted(payload):
        _label(key, f"{where} key {key!r}")
        out[key] = _probability(payload[key], f"{where}[{key!r}]")
        total += out[key]
    if abs(total - 1.0) > DISTRIBUTION_SUM_TOLERANCE:
        raise ContractError(
            "value-invalid",
            f"{where} sums to {total!r}, not 1 within the documented tolerance of "
            f"{DISTRIBUTION_SUM_TOLERANCE}; a distribution this far off is refused, never "
            f"renormalised back to 1",
        )
    return out


def _answer(value, spec, where, *, answers_required):
    """One answer. `answers_required` is true only inside an `ok` result.

    That distinction is the whole meaning of `abstention: forbidden`. It says an `ok` result
    must carry a value for this question -- not that a provider is obliged to have one. A
    provider with nothing to say returns status `abstain` for the WHOLE result, and may list
    its abstentions there, including on questions an `ok` result would have had to answer.
    """
    payload = _closed(value, _ANSWER_KEYS, where)
    abstained = _bool(payload["abstained"], f"{where}.abstained")
    outcome = payload["outcome"]
    if abstained:
        if answers_required and spec.abstention != "permitted":
            raise ContractError(
                "missing-answer",
                f"{where} abstains on {spec.qualified_id!r}, whose spec marks the answer "
                f"required; a provider with nothing to say returns status 'abstain' for the "
                f"whole result rather than a partial one",
            )
        if outcome is not None:
            raise ContractError(
                "value-invalid",
                f"{where} is abstained and also carries the outcome {outcome!r}; it is one or "
                f"the other",
            )
    else:
        if outcome is None:
            raise ContractError("missing-answer",
                                f"{where} is not abstained and carries no outcome")
        _label(outcome, f"{where}.outcome")
        if outcome not in spec.outcomes:
            raise ContractError(
                "unknown-value",
                f"{where}.outcome is {outcome!r}; {spec.qualified_id!r} permits "
                f"{list(spec.outcomes)}",
            )
    confidence = payload["vendor_confidence"]
    if confidence is not None:
        # Deliberately unbounded in range. A vendor's own score is not a probability of task
        # success, and clamping it to [0, 1] here would dress one up as the other.
        _number(confidence, f"{where}.vendor_confidence")
    return {
        "outcome": outcome, "abstained": abstained,
        "raw": _distribution(payload["raw"], f"{where}.raw", outcomes=spec.outcomes),
        "calibrated": _distribution(payload["calibrated"], f"{where}.calibrated",
                                    outcomes=spec.outcomes),
        "vendor_confidence": confidence,
    }


def _duration(value, where):
    if value is None:
        return None
    history = _ah()
    payload = _closed(value, ("basis", "seconds", "source"), where)
    basis = _one_of(payload["basis"], history.DURATION_BASES, f"{where}.basis")
    if basis != DECISION_DURATION_BASIS:
        raise ContractError(
            "unknown-value",
            f"{where}.basis is {basis!r}; a decision's own latency is recorded on "
            f"{DECISION_DURATION_BASIS!r}, and the other bases are other clocks measuring other "
            f"things",
        )
    seconds = (None if payload["seconds"] is None
               else _number(payload["seconds"], f"{where}.seconds", minimum=0))
    source = _text(payload["source"], f"{where}.source", minimum=0, limit=MAX_ID_CHARS)
    built = history._duration(basis, seconds, source)
    if set(built) != set(payload):
        raise ContractError("unknown-field",
                            f"{where} does not match the projection's duration shape")
    return built


def _usage(value, where):
    """Resource use on the basis its own projection already names. Never a second money field."""
    if value is None:
        return None
    history = _ah()
    payload = _closed(value, ("basis", "usd", "credits", "source"), where)
    basis = _one_of(payload["basis"], history.COST_BASES, f"{where}.basis")
    usd = None if payload["usd"] is None else _number(payload["usd"], f"{where}.usd", minimum=0)
    credits = (None if payload["credits"] is None
               else _number(payload["credits"], f"{where}.credits", minimum=0))
    source = _text(payload["source"], f"{where}.source", minimum=0, limit=MAX_ID_CHARS)
    return history._cost(basis, usd, credits, source)


def parse_result(value, request, where="result"):
    """A provider's answer, refused unless it answers THIS request."""
    if not isinstance(request, DecisionRequest):
        raise ContractError(
            "wrong-type",
            "a result is only meaningful against the request it answers; pass the parsed "
            "DecisionRequest, not a payload",
        )
    payload = _closed(value, _RESULT_KEYS, where)
    if payload["v"] != CONTRACT_VERSION:
        raise ContractError("unknown-value",
                            f"{where}.v is {payload['v']!r}; this parser reads {CONTRACT_VERSION}")

    # Identity FIRST, and before the status is even looked at. A terminal status is still an
    # answer to one particular request: a timeout correlated to another call is not this call's
    # timeout, and letting it through would close a live request on someone else's failure.
    correlation_id = _label(payload["correlation_id"], f"{where}.correlation_id")
    if correlation_id != request.correlation_id:
        raise ContractError(
            "correlation-mismatch",
            f"{where}.correlation_id is {correlation_id!r} but the request is "
            f"{request.correlation_id!r}",
        )
    state_sha = _digest(payload["state_sha"], f"{where}.state_sha")
    if state_sha != request.state_sha:
        raise ContractError(
            "state-mismatch",
            f"{where}.state_sha is {state_sha} but the request was asked about "
            f"{request.state_sha}; the world moved under the answer",
        )
    questions_sha = _digest(payload["questions_sha"], f"{where}.questions_sha")
    if questions_sha != request.questions_sha:
        raise ContractError(
            "state-mismatch",
            f"{where}.questions_sha is {questions_sha} but the request asked "
            f"{request.questions_sha}; this answers a different question set",
        )

    status = _one_of(payload["status"], RESULT_STATUSES, f"{where}.status")
    specs = request.question_by_qualified_id()
    raw_answers = _object(payload["answers"], f"{where}.answers")

    if status in TERMINAL_STATUSES:
        if raw_answers:
            raise ContractError(
                "value-invalid",
                f"{where}.status is {status!r} and carries {len(raw_answers)} answer(s); a "
                f"terminal status reports that nothing was answered",
            )
        if payload["recommended"] is not None:
            raise ContractError(
                "value-invalid",
                f"{where}.status is {status!r} and still recommends "
                f"{payload['recommended']!r}",
            )

    answers = {}
    for key in sorted(raw_answers):
        if key not in specs:
            raise ContractError(
                "unknown-question",
                f"{where}.answers has {key!r}, which this request does not ask. An answer is "
                f"filed under 'id@version', so a question that was reworded no longer matches "
                f"and its old answer is not silently reused",
            )
        answers[key] = _answer(raw_answers[key], specs[key], f"{where}.answers[{key!r}]",
                               answers_required=status == "ok")

    if status == "ok":
        missing = sorted(set(specs) - set(answers))
        if missing:
            raise ContractError(
                "missing-answer",
                f"{where}.status is 'ok' but {', '.join(repr(m) for m in missing)} went "
                f"unanswered; an 'ok' result answers every question it was asked",
            )
    elif status == "abstain":
        answered = sorted(key for key, ans in answers.items() if not ans["abstained"])
        if answered:
            raise ContractError(
                "value-invalid",
                f"{where}.status is 'abstain' but {', '.join(repr(a) for a in answered)} "
                f"carries an outcome; an abstaining result holds no values",
            )
        if payload["recommended"] is not None:
            raise ContractError(
                "value-invalid",
                f"{where}.status is 'abstain' and still recommends "
                f"{payload['recommended']!r}; abstention is the absence of a judgement",
            )

    recommended = payload["recommended"]
    if recommended is not None:
        _label(recommended, f"{where}.recommended")
        if recommended not in request.alternatives:
            raise ContractError(
                "unknown-action",
                f"{where}.recommended is {recommended!r}, which is not one of the eligible "
                f"alternatives {list(request.alternatives)}. A provider chooses among what it "
                f"was offered; it does not widen the set",
            )

    raw_refs = _sequence(payload["evidence_refs"], f"{where}.evidence_refs",
                         maximum=MAX_EVIDENCE_REFS)
    evidence = tuple(_frozen_map(_ref(item, f"{where}.evidence_refs[{index}]"))
                     for index, item in enumerate(raw_refs))

    identities = {}
    for name in ("requested_provider", "dispatched_provider", "observed_provider",
                 "requested_model", "dispatched_model", "observed_model",
                 "provider_contract_v"):
        item = payload[name]
        identities[name] = None if item is None else _label(item, f"{where}.{name}")

    note = (None if payload["note"] is None
            else _text(payload["note"], f"{where}.note", minimum=0, limit=MAX_TEXT_CHARS))

    return DecisionResult(
        v=CONTRACT_VERSION, correlation_id=correlation_id, state_sha=state_sha,
        questions_sha=questions_sha, status=status,
        answers=_frozen_map({key: _frozen_map(value) for key, value in answers.items()}),
        recommended=recommended, evidence_refs=evidence,
        duration=_duration(payload["duration"], f"{where}.duration"),
        usage=_usage(payload["usage"], f"{where}.usage"), note=note, **identities,
    )


# ---- DecisionRecord --------------------------------------------------------------------------------

_REJECTED_KEYS = ("action", "reason")
_RECORD_KEYS = ("v", "correlation_id", "decision_id", "mode", "baseline", "recommended",
                "selected", "bundle_sha", "reason_codes", "rejected", "result_status",
                "admission_ref", "attempt_ref", "duration")


@dataclasses.dataclass(frozen=True)
class DecisionRecord:
    """What the coordinator DID, and under which grant it was entitled to do it.

    Only a coordinator composes one. `build_record` takes the fields nobody else may supply as
    keyword-only arguments, and `parse_record` cannot be called without the request and result
    the record closes over -- so a provider payload, however well formed, can never become a
    record. The advice is an input to this object; it is never this object.
    """

    v: str
    correlation_id: str
    decision_id: str
    mode: str
    baseline: str
    recommended: object
    selected: str
    bundle_sha: object
    reason_codes: tuple
    rejected: tuple
    result_status: str
    admission_ref: types.MappingProxyType
    attempt_ref: object
    duration: object

    def to_payload(self):
        return {
            "v": self.v, "correlation_id": self.correlation_id, "decision_id": self.decision_id,
            "mode": self.mode, "baseline": self.baseline, "recommended": self.recommended,
            "selected": self.selected, "bundle_sha": self.bundle_sha,
            "reason_codes": list(self.reason_codes),
            "rejected": [dict(item) for item in self.rejected],
            "result_status": self.result_status,
            "admission_ref": dict(self.admission_ref),
            "attempt_ref": None if self.attempt_ref is None else dict(self.attempt_ref),
            "duration": None if self.duration is None else dict(self.duration),
        }

    def sha(self):
        return _sha(_canonical(self.to_payload()))


def parse_record(value, request, result, where="record"):
    """Read a record back, against the request and result it was written about."""
    if not isinstance(request, DecisionRequest) or not isinstance(result, DecisionResult):
        raise ContractError(
            "wrong-type",
            "a record is only meaningful against its request and result; there is deliberately "
            "no context-free record parser, because a record read without them cannot be "
            "checked for the things that make it a record",
        )
    payload = _closed(value, _RECORD_KEYS, where)
    if payload["v"] != CONTRACT_VERSION:
        raise ContractError("unknown-value",
                            f"{where}.v is {payload['v']!r}; this parser reads {CONTRACT_VERSION}")

    correlation_id = _label(payload["correlation_id"], f"{where}.correlation_id")
    if correlation_id != request.correlation_id:
        raise ContractError(
            "correlation-mismatch",
            f"{where}.correlation_id is {correlation_id!r} but the request is "
            f"{request.correlation_id!r}",
        )
    if result.correlation_id != request.correlation_id:
        raise ContractError(
            "correlation-mismatch",
            f"{where} closes over a result correlated to {result.correlation_id!r} and a "
            f"request correlated to {request.correlation_id!r}",
        )

    decision_id = _label(payload["decision_id"], f"{where}.decision_id")
    mode = _one_of(payload["mode"], DECISION_MODES, f"{where}.mode")

    actions = {}
    for name in ("baseline", "selected"):
        action = _label(payload[name], f"{where}.{name}")
        if action not in request.alternatives:
            raise ContractError(
                "unknown-action",
                f"{where}.{name} is {action!r}, which is not one of the eligible alternatives "
                f"{list(request.alternatives)}",
            )
        actions[name] = action

    recommended = payload["recommended"]
    if recommended is not None:
        _label(recommended, f"{where}.recommended")
        if recommended not in request.alternatives:
            raise ContractError(
                "unknown-action",
                f"{where}.recommended is {recommended!r}, which is not one of "
                f"{list(request.alternatives)}",
            )
    if recommended != result.recommended:
        raise ContractError(
            "value-invalid",
            f"{where}.recommended is {recommended!r} but the result recommended "
            f"{result.recommended!r}; a record reports the advice it got and never improves it",
        )

    if payload["result_status"] != result.status:
        raise ContractError(
            "value-invalid",
            f"{where}.result_status is {payload['result_status']!r} but the result's status is "
            f"{result.status!r}",
        )
    result_status = _one_of(payload["result_status"], RESULT_STATUSES, f"{where}.result_status")

    bundle_sha = _digest(payload["bundle_sha"], f"{where}.bundle_sha", optional=True)
    reason_codes = _unique_labels(payload["reason_codes"], f"{where}.reason_codes",
                                  maximum=MAX_REASON_CODES, minimum=1)

    raw_rejected = _sequence(payload["rejected"], f"{where}.rejected",
                             maximum=MAX_ALTERNATIVES)
    rejected = []
    seen = set()
    for index, item in enumerate(raw_rejected):
        entry = _closed(item, _REJECTED_KEYS, f"{where}.rejected[{index}]")
        action = _label(entry["action"], f"{where}.rejected[{index}].action")
        if action not in request.alternatives:
            raise ContractError(
                "unknown-action",
                f"{where}.rejected[{index}].action is {action!r}, which was never eligible",
            )
        if action == actions["selected"]:
            raise ContractError(
                "value-invalid",
                f"{where}.rejected lists the selected action {action!r}",
            )
        if action in seen:
            raise ContractError("duplicate-entry",
                                f"{where}.rejected repeats {action!r}")
        seen.add(action)
        rejected.append(_frozen_map(
            {"action": action,
             "reason": _label(entry["reason"], f"{where}.rejected[{index}].reason")}))

    admission_ref = _ref(payload["admission_ref"], f"{where}.admission_ref")
    if admission_ref["id"] == request.admission_ref["id"]:
        raise ContractError(
            "stale-admission",
            f"{where}.admission_ref reuses {admission_ref['id']!r}, the grant that admitted the "
            f"DECISION call. Acting on the answer is a separate operation and needs its own "
            f"fresh, atomic admission taken just before the action -- the request's grant is "
            f"already spent on asking",
        )
    attempt_ref = _ref(payload["attempt_ref"], f"{where}.attempt_ref", optional=True)

    return DecisionRecord(
        v=CONTRACT_VERSION, correlation_id=correlation_id, decision_id=decision_id, mode=mode,
        baseline=actions["baseline"], recommended=recommended, selected=actions["selected"],
        bundle_sha=bundle_sha, reason_codes=reason_codes, rejected=tuple(rejected),
        result_status=result_status, admission_ref=_frozen_map(admission_ref),
        attempt_ref=None if attempt_ref is None else _frozen_map(attempt_ref),
        duration=_duration(payload["duration"], f"{where}.duration"),
    )


def build_record(request, result, *, decision_id, mode, baseline, selected, admission_ref,
                 reason_codes, bundle_sha=None, rejected=(), attempt_ref=None,
                 duration_s=None, duration_source=""):
    """The ONE way a DecisionRecord comes into being, and it is the coordinator's.

    Every field a provider could have an opinion about is keyword-only and supplied by the
    caller, never lifted out of `result`. `recommended` and `result_status` are the two fields
    copied from the result, because reporting what the advice WAS is the record's job; choosing
    is not the advice's.
    """
    payload = {
        "v": CONTRACT_VERSION,
        "correlation_id": request.correlation_id,
        "decision_id": decision_id,
        "mode": mode,
        "baseline": baseline,
        "recommended": result.recommended,
        "selected": selected,
        "bundle_sha": bundle_sha,
        "reason_codes": list(reason_codes),
        "rejected": [dict(item) for item in rejected],
        "result_status": result.status,
        "admission_ref": None if admission_ref is None else dict(admission_ref),
        "attempt_ref": None if attempt_ref is None else dict(attempt_ref),
        "duration": (None if duration_s is None
                     else _ah()._duration(DECISION_DURATION_BASIS, duration_s, duration_source)),
    }
    return parse_record(payload, request, result)


def decision_ref(record):
    """The pointer an attempt event carries at `decision_ref`, built by the ledger's own maker.

    The version in it is `CONTRACT_VERSION` -- the referenced object's -- never the ledger's.
    The ledger line versions the event; this versions what the event points at, and a reader
    that fetched the record needs to know which field names apply to IT.
    """
    if not isinstance(record, DecisionRecord):
        raise ContractError("wrong-type", "decision_ref takes a DecisionRecord")
    return _al().make_ref(record.decision_id, sha=record.sha(), version=CONTRACT_VERSION)


# ==================================================================================================
#  D11 -- POLICY BUNDLES AND CANDIDATE PROPOSALS
# ==================================================================================================
#
# D09's four objects describe ONE decision. These two describe the POLICY a decision was taken
# under, and a bounded request to change it.
#
#   * `PolicyBundle`      -- an immutable, content-addressed statement of which data parameters
#                            apply, to what, under which component versions and requirements,
#                            and what runtime falls back to when it cannot be used.
#   * `CandidateProposal` -- a falsifiable request to change those parameters, carrying the
#                            evidence AND the counterevidence, an evaluation it must pass, and
#                            the target a rollback returns to.
#
# WHAT A BUNDLE IS NOT. It is not an approval, a permission, a budget or an activation. Nothing
# here can be read as "and therefore this may now run": the fields that would say so are refused
# by `BANNED_FIELDS` like everywhere else in this module, `provenance.approval_ref` is a POINTER
# at a record some other authority owns rather than the approval itself, and selecting a bundle
# is `bin/decision_policy.py`'s pure, side-effect-free resolution -- which writes nothing,
# activates nothing, and falls back to the frozen legacy behaviour whenever anything is unmet.
# Runtime activation is a separately gated transition owned by the evaluation workbench.
#
# WHY THE HISTORICAL PREFERENCE SHAPE IS REFUSED HERE BY NAME. The evaluation workbench has long
# written a pull-only preference payload recording which defaults its own evidence supports. No
# driver reads it, on purpose. That payload names no parent, no scope, no component versions, no
# requirements and no fallback, so reading one as a bundle would silently promote a file nothing
# consumes into the thing every run pins -- which is exactly the transition the plan reserves for
# an explicit, approved, versioned opt-in. `parse_bundle` therefore refuses it with a message
# that says what it is, and `is_legacy_preference_payload` is the machine-readable side of that
# refusal so a caller can tell "this is the old shape" apart from "this is malformed".
#
# WHAT THE BAN STILL DOES NOT COVER HERE. `_reject_banned` sweeps MAPPING KEYS, through
# `_object`, and list ITEMS are not swept -- which was true before these two records and is
# still true. A parameter map cannot hide one, because every parameter value is a scalar of a
# declared kind and a list or nested object is refused by type. But a scope's `task_classes`, a
# requirement's `capabilities` and `providers`, and the evidence lists are lists, and an entry
# in one of them spelled like a banned name PARSES. Those entries are compared for membership
# and nothing more -- a cohort called `approve` selects the cohort called `approve` -- so this
# is a naming oddity rather than an authority, and it is written down here so nobody reads the
# ban as covering more than it does. The homoglyph non-guarantee `_is_banned_key` states
# applies unchanged.
#
# TWO VERSIONS, NOT ONE, AND NEITHER IS `CONTRACT_VERSION`. A bundle and a proposal change on
# their own schedules and neither is one of D09's four objects, so overloading
# `polytropos.decision/1` would make a decision-shape change look like a policy-shape change and
# vice versa. Both are registered in `release_gate.VERSION_SOURCES` in their own right.

#: Ceiling on how many task classes, capabilities or providers one bundle may enumerate.
MAX_SCOPE_ENTRIES = 32
MAX_REQUIREMENT_ENTRIES = 16

#: Ceiling on a `count` parameter's value. A data parameter is a small dial, never a budget:
#: nothing here can raise a ceiling, so this bound exists to keep a "count" from being used as a
#: smuggled size for something else.
MAX_PARAMETER_VALUE = 64

#: The fewest supporting references a candidate proposal may cite. One attempt is an anecdote,
#: and the plan asks for RECURRING evidence; two is the smallest number that can recur. It is a
#: floor on citation, never a claim that two attempts are sufficient evidence for anything.
MIN_EVIDENCE_REFS = 2

#: A hypothesis, a falsification and a tradeoff are sentences, not labels -- the same floor
#: `MIN_QUESTION_CHARS`/`MIN_QUESTION_WORDS` put under a question's wording, for the same reason.
MIN_STATEMENT_CHARS = 32
MIN_STATEMENT_WORDS = 6

#: The version of `PolicyBundle`, on the referenced object rather than on any envelope that
#: carries it -- the precedent D04 set when it showed that bumping the ledger's own version
#: silently discards every stored attempt.
BUNDLE_VERSION = "polytropos.policy-bundle/1"

#: The version of `CandidateProposal`. Separate from the bundle's because a proposal's shape can
#: gain a field -- an evaluation input, say -- without every stored bundle becoming unreadable.
CANDIDATE_VERSION = "polytropos.candidate-proposal/1"

#: The version string the evaluation workbench's historical preference payload carries. Declared
#: here so `parse_bundle` can refuse that shape BY NAME rather than as generic noise, and so a
#: reader learns the two are different things. This module never reads, writes or locates that
#: file -- the workbench owns it, `tests/test_decision_policy_bundle.py` pins this constant
#: against the workbench's own so the two cannot drift apart, and nothing here converts one.
LEGACY_PREFERENCE_VERSION = "polytropos.routing-policy/1"

#: What a bundle falls back to. `legacy` is the frozen existing behaviour and is always
#: reachable; `bundle` names a previously approved compatible bundle by pinned reference. There
#: is deliberately no third kind meaning "nothing", because "no fallback" is how an unusable
#: bundle turns into a stalled run instead of a legacy one.
FALLBACK_KINDS = ("legacy", "bundle")

#: The value kinds a data parameter may take. All three are SCALARS. A list or a nested object
#: is refused by type -- which is also why the ban's mapping-key-only sweep is not a hole here:
#: a diff has no list and no nested map for it to miss.
PARAMETER_KINDS = ("boolean", "count", "label")

#: The ALLOWLIST: every data parameter a bundle may carry and a proposal may change, with the
#: kind of value it takes. This is the mechanical form of "no candidate edits arbitrary Python,
#: shell, module paths, acceptance, permissions, pricing, the improvement procedure or hidden
#: evaluation rules" -- not by listing those, which would be a blocklist and therefore a guess,
#: but by enumerating the few data dials that are permitted at all. A key outside it is refused
#: as unknown; a key inside `BANNED_FIELDS` is refused earlier still, as an authority field.
#:
#: One allowlist, two users. A bundle's `parameters` and a proposal's `diff` are validated by the
#: same function against this same mapping, so the set of things a candidate may propose is
#: exactly the set of things a bundle may carry, and neither side can grow without the other.
#:
#: The VALUES a label parameter may take are the owning surface's vocabulary, not this
#: contract's: whether a workflow name is a workflow the evaluator knows is the evaluator's
#: question, asked where that vocabulary lives.
DIFF_PARAMETERS = {
    "recovery.contract_context_package": "boolean",
    "recovery.contract_context_files": "count",
    "routing.default_workflow": "label",
    "routing.default_policy": "label",
}

#: The partitions whose results may be cited as evidence for a change. These are the workbench's
#: held-out partitions and nothing else: material a fit has touched is spent, so a proposal
#: evaluated on a fitting partition is citing the fit. The workbench owns the four partitions and
#: their roles; this names the subset a proposal may point at, and a test pins the two together.
EVIDENCE_PARTITIONS = ("promotion", "audit")

#: A contract version string is not an identifier: it carries a '/' that `_ID_RE` refuses, on
#: purpose, because the two are different kinds of name.
_VERSION_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._/-]*\Z")

_SCOPE_KEYS = ("project", "task_classes", "intended_uses")
COMPONENT_KEYS = ("decision_contract", "task_contract", "provider_contract")
_REQUIREMENT_KEYS = ("capabilities", "providers", "calibration")
_FALLBACK_KEYS = ("kind", "bundle_ref")
_PROVENANCE_KEYS = ("approval_ref", "evaluation_ref", "rolled_back_from")
_BUNDLE_KEYS = ("v", "id", "parent", "scope", "components", "parameters", "requirements",
                "fallback", "provenance")
_EVALUATION_KEYS = ("endpoint", "partition", "manifest_ref")
_CANDIDATE_KEYS = ("v", "id", "parent", "hypothesis", "falsification", "tradeoff", "scope",
                   "diff", "evaluation", "evidence", "counterevidence", "rollback")


# ---- D11 primitives -------------------------------------------------------------------------

def _version(value, where):
    """A contract version string -- `name/N` -- which `_label` would refuse for its slash."""
    if not isinstance(value, str):
        raise ContractError("wrong-type", f"{where} must be a string, got {type(value).__name__}")
    if not value:
        raise ContractError("value-invalid", f"{where} is empty")
    if len(value) > MAX_ID_CHARS:
        raise ContractError("bounds-exceeded",
                            f"{where} is {len(value)} chars; the limit is {MAX_ID_CHARS}")
    if not _VERSION_RE.match(value):
        raise ContractError(
            "value-invalid",
            f"{where} is {value!r}; a contract version starts alphanumeric and uses only "
            f"letters, digits, '.', '_', '-' and '/'",
        )
    return value


def _pinned_ref(value, where, *, optional=False, version=None):
    """A reference that PINS content: id, digest and referenced version, none of them absent.

    `attempt_ledger.make_ref` permits a digest-free pointer, because a caller may honestly not
    know one -- and for an event's provenance, absent is the honest record. A bundle's lineage
    is the opposite case: a parent, a fallback or an evidence item that does not pin the exact
    bytes it names cannot detect that those bytes changed underneath it, and detecting exactly
    that is what these pointers are FOR. So the same reference shape is required complete here.
    A digest identifies content and prevents nothing; what it buys is that a rewrite is visible.
    """
    if value is None:
        if optional:
            return None
        raise ContractError("not-a-reference", f"{where} is required and is null")
    ref = _ref(value, where)
    if ref["sha"] is None:
        raise ContractError(
            "value-invalid",
            f"{where} names {ref['id']!r} without the digest of the bytes it names; a pointer "
            f"that pins no content cannot notice the content changing under it",
        )
    if ref["v"] is None:
        raise ContractError(
            "value-invalid",
            f"{where} names {ref['id']!r} without the referenced contract's version; a reader "
            f"that fetches it would not know which field names apply to what it got",
        )
    if version is not None and ref["v"] != version:
        raise ContractError(
            "unknown-value",
            f"{where} points at a {ref['v']!r} object; this slot points at {version!r}",
        )
    return ref


def _statement(value, where):
    """A sentence, not a label. The floor a question's wording already has, for one reason."""
    text = _text(value, where, minimum=MIN_STATEMENT_CHARS)
    if len(text.split()) < MIN_STATEMENT_WORDS:
        raise ContractError(
            "value-invalid",
            f"{where} is {len(text.split())} words; at least {MIN_STATEMENT_WORDS} are needed "
            f"for this to be a statement somebody could disagree with rather than a label",
        )
    return text


def _parameters(value, where, *, minimum=0):
    """The data parameters a bundle carries or a proposal changes, against ONE allowlist.

    Refusals, in the order they can happen: a banned key (via `_object`, so an authority field
    is refused before anything else is looked at), a key outside `DIFF_PARAMETERS`, and a value
    of the wrong kind. Nothing is coerced -- a `"1"` offered for a count is refused, not read as
    one, because a provider or proposer that sent a string did not mean an integer.
    """
    payload = _object(value, where)
    if len(payload) < minimum:
        raise ContractError(
            "bounds-exceeded",
            f"{where} sets {len(payload)} parameter(s); at least {minimum} are needed for this "
            f"to be a proposal to change something",
        )
    if len(payload) > len(DIFF_PARAMETERS):
        raise ContractError(
            "bounds-exceeded",
            f"{where} sets {len(payload)} parameter(s); the allowlist has "
            f"{len(DIFF_PARAMETERS)}",
        )
    out = {}
    for key in sorted(payload):
        kind = DIFF_PARAMETERS.get(key)
        if kind is None:
            raise ContractError(
                "unknown-field",
                f"{where} sets {key!r}, which is not one of the data parameters policy may "
                f"carry ({', '.join(sorted(DIFF_PARAMETERS))}). Code, a command, a module path, "
                f"an acceptance criterion, a permission, a price and an evaluation rule are each "
                f"owned by an authority outside this payload and none of them is settable here",
            )
        item = payload[key]
        if kind == "boolean":
            out[key] = _bool(item, f"{where}[{key!r}]")
        elif kind == "count":
            count = _integer(item, f"{where}[{key!r}]", minimum=0)
            if count > MAX_PARAMETER_VALUE:
                raise ContractError(
                    "bounds-exceeded",
                    f"{where}[{key!r}] is {count}; the limit is {MAX_PARAMETER_VALUE}",
                )
            out[key] = count
        else:
            out[key] = _label(item, f"{where}[{key!r}]")
    return out


def _scope(value, where):
    """What this bundle or proposal applies TO. Enumerated, never wildcarded.

    There is deliberately no "everything" token. A bundle that means every task class lists
    them, which is longer and which someone has to look at -- and a wildcard is how a change
    scoped to one cohort silently becomes a change to all of them.
    """
    payload = _closed(value, _SCOPE_KEYS, where)
    project = _label(payload["project"], f"{where}.project")
    classes = _unique_labels(payload["task_classes"], f"{where}.task_classes",
                             maximum=MAX_SCOPE_ENTRIES, minimum=1)
    uses = _unique_labels(payload["intended_uses"], f"{where}.intended_uses",
                          maximum=len(INTENDED_USES), minimum=1)
    for index, use in enumerate(uses):
        _one_of(use, INTENDED_USES, f"{where}.intended_uses[{index}]")
    return _frozen_map({"project": project, "task_classes": classes, "intended_uses": uses})


def _components(value, where, *, providers):
    """The contract versions a run must match to use this bundle.

    A version pinned here is a REQUIREMENT, not a claim about the present: an old bundle pins
    old versions, still parses, and simply stops resolving. `provider_contract` may be null,
    which is the offline case and the V1 default -- but a bundle that REQUIRES a provider may
    not leave it null, because requiring a provider without pinning the contract you speak to it
    with is requiring an unknown.
    """
    payload = _closed(value, COMPONENT_KEYS, where)
    out = {}
    for key in COMPONENT_KEYS:
        item = payload[key]
        out[key] = None if item is None else _version(item, f"{where}[{key!r}]")
    for key in ("decision_contract", "task_contract"):
        if out[key] is None:
            raise ContractError(
                "missing-field",
                f"{where}[{key!r}] is null; this bundle's own fields are read by that contract's "
                f"parser, so the version it was written against is never unknown",
            )
    if providers and out["provider_contract"] is None:
        raise ContractError(
            "missing-field",
            f"{where}['provider_contract'] is null while the bundle requires provider(s) "
            f"{', '.join(repr(p) for p in providers)}; a required provider without the contract "
            f"version to speak to it with is a requirement nothing can check",
        )
    return _frozen_map(out)


def _requirements(value, where):
    """What must be TRUE ELSEWHERE before this bundle may be used.

    None of it is checked here, and saying so is the point. A capability is verified in the
    registry that owns capability evidence -- where `unknown` means no -- provider eligibility
    is the coordinator's fresh check just before acting, and a calibrator is fetched from the
    store that holds it. This records WHICH facts a resolver must go and establish.
    """
    payload = _closed(value, _REQUIREMENT_KEYS, where)
    capabilities = _unique_labels(payload["capabilities"], f"{where}.capabilities",
                                  maximum=MAX_REQUIREMENT_ENTRIES)
    providers = _unique_labels(payload["providers"], f"{where}.providers",
                               maximum=MAX_PROVIDERS)
    calibration = _pinned_ref(payload["calibration"], f"{where}.calibration", optional=True)
    return _frozen_map({
        "capabilities": capabilities, "providers": providers,
        "calibration": None if calibration is None else _frozen_map(calibration),
    })


def _fallback(value, where):
    """What runtime uses when this bundle cannot be used. Required, and never nothing."""
    payload = _closed(value, _FALLBACK_KEYS, where)
    kind = _one_of(payload["kind"], FALLBACK_KINDS, f"{where}.kind")
    pointer = payload["bundle_ref"]
    if kind == "legacy":
        if pointer is not None:
            raise ContractError(
                "value-invalid",
                f"{where} falls back to the frozen legacy behaviour and also names "
                f"{pointer!r}; it is one or the other",
            )
        return _frozen_map({"kind": kind, "bundle_ref": None})
    ref = _pinned_ref(pointer, f"{where}.bundle_ref", version=BUNDLE_VERSION)
    return _frozen_map({"kind": kind, "bundle_ref": _frozen_map(ref)})


def _provenance(value, where):
    """Where this bundle's authority is recorded -- never the authority itself.

    `approval_ref` is a pointer at a record the promotion lifecycle owns. Its PRESENCE is a
    necessary condition and never a sufficient one: a reference is not authentication and a
    digest is not an approval, so the exact binding of reviewer, scope and evaluation hashes
    stays with the lifecycle that owns it. What this rules out is a bundle that points at no
    approval at all being selected by accident.
    """
    payload = _closed(value, _PROVENANCE_KEYS, where)
    approval = _pinned_ref(payload["approval_ref"], f"{where}.approval_ref", optional=True)
    evaluation = _pinned_ref(payload["evaluation_ref"], f"{where}.evaluation_ref", optional=True)
    rolled_back = _pinned_ref(payload["rolled_back_from"], f"{where}.rolled_back_from",
                              optional=True, version=BUNDLE_VERSION)
    if approval is not None and evaluation is None:
        raise ContractError(
            "missing-field",
            f"{where}.approval_ref names an approval while {where}.evaluation_ref is null; what "
            f"was approved was approved on the strength of something, and an approval with no "
            f"evaluation behind it records a decision nobody can check",
        )
    return _frozen_map({
        "approval_ref": None if approval is None else _frozen_map(approval),
        "evaluation_ref": None if evaluation is None else _frozen_map(evaluation),
        "rolled_back_from": None if rolled_back is None else _frozen_map(rolled_back),
    })


def _declared_version(value, where):
    """The `v` a payload declares, before anything else is read from it."""
    payload = _object(value, where)
    if "v" not in payload:
        raise ContractError("missing-field",
                            f"{where} is missing 'v'; nothing can be read from a payload that "
                            f"does not say which contract wrote it")
    version = payload["v"]
    if not isinstance(version, str):
        raise ContractError("wrong-type",
                            f"{where}.v must be a string, got {type(version).__name__}")
    return payload, version


def is_legacy_preference_payload(value):
    """Is this the evaluation workbench's historical, pull-only preference payload?

    The machine-readable half of `parse_bundle`'s refusal: it lets a caller tell "this is the
    old shape, which is real and readable and simply is not a bundle" apart from "this payload
    is malformed", without branching on a message. Nothing in this repository converts one into
    a bundle; re-proposing the change through the workbench is how it would ever become one.
    """
    return isinstance(value, dict) and value.get("v") == LEGACY_PREFERENCE_VERSION


# ---- PolicyBundle ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class PolicyBundle:
    """An immutable, content-addressed statement of which data parameters apply, and to what.

    Its identity is its content: `sha()` is taken over the canonical form of every field, so two
    bundles agree iff they say the same thing, and a rewrite is a different bundle rather than
    the same one changed. The digest is not a protection -- anything running with the user's
    privileges can rewrite a payload and recompute it -- it is what makes a rewrite VISIBLE to
    the pin that named the old bytes.
    """

    v: str
    id: str
    parent: object
    scope: types.MappingProxyType
    components: types.MappingProxyType
    parameters: types.MappingProxyType
    requirements: types.MappingProxyType
    fallback: types.MappingProxyType
    provenance: types.MappingProxyType

    def to_payload(self):
        requirements = dict(self.requirements)
        provenance = dict(self.provenance)
        return {
            "v": self.v,
            "id": self.id,
            "parent": None if self.parent is None else dict(self.parent),
            "scope": {"project": self.scope["project"],
                      "task_classes": list(self.scope["task_classes"]),
                      "intended_uses": list(self.scope["intended_uses"])},
            "components": dict(self.components),
            "parameters": dict(self.parameters),
            "requirements": {
                "capabilities": list(requirements["capabilities"]),
                "providers": list(requirements["providers"]),
                "calibration": (None if requirements["calibration"] is None
                                else dict(requirements["calibration"])),
            },
            "fallback": {"kind": self.fallback["kind"],
                         "bundle_ref": (None if self.fallback["bundle_ref"] is None
                                        else dict(self.fallback["bundle_ref"]))},
            "provenance": {key: (None if provenance[key] is None else dict(provenance[key]))
                           for key in _PROVENANCE_KEYS},
        }

    def sha(self):
        return _sha(_canonical(self.to_payload()))


def parse_bundle(value, where="bundle"):
    """A policy bundle, refused unless it is complete, self-consistent and not something else."""
    payload, version = _declared_version(value, where)
    if version == LEGACY_PREFERENCE_VERSION:
        raise ContractError(
            "unknown-value",
            f"{where} is a {LEGACY_PREFERENCE_VERSION} preference payload, not a "
            f"{BUNDLE_VERSION} bundle. That shape is pull-only advice about defaults: it names "
            f"no parent, no scope, no component versions, no requirements and no fallback, and "
            f"reading one as a bundle would promote a file nothing consumes into the thing every "
            f"run pins. Re-propose the change through the workbench that owns it",
        )
    if version != BUNDLE_VERSION:
        raise ContractError(
            "unknown-value",
            f"{where}.v is {version!r}; this parser reads {BUNDLE_VERSION} and refuses to guess "
            f"at another shape's field meanings",
        )
    payload = _closed(payload, _BUNDLE_KEYS, where)
    bundle_id = _label(payload["id"], f"{where}.id")

    parent = _pinned_ref(payload["parent"], f"{where}.parent", optional=True,
                         version=BUNDLE_VERSION)
    if parent is not None and parent["id"] == bundle_id:
        raise ContractError(
            "value-invalid",
            f"{where}.parent names {bundle_id!r}, the bundle itself; a lineage that contains a "
            f"cycle has no root, and there would be nothing to compare this bundle against",
        )

    scope = _scope(payload["scope"], f"{where}.scope")
    requirements = _requirements(payload["requirements"], f"{where}.requirements")
    components = _components(payload["components"], f"{where}.components",
                             providers=requirements["providers"])
    parameters = _parameters(payload["parameters"], f"{where}.parameters")

    fallback = _fallback(payload["fallback"], f"{where}.fallback")
    if (fallback["bundle_ref"] is not None
            and fallback["bundle_ref"]["id"] == bundle_id):
        raise ContractError(
            "value-invalid",
            f"{where}.fallback falls back to {bundle_id!r}, itself; resolving it would arrive "
            f"back where it started and the chain would never reach the legacy behaviour",
        )

    provenance = _provenance(payload["provenance"], f"{where}.provenance")
    rolled_back = provenance["rolled_back_from"]
    if rolled_back is not None and rolled_back["id"] == bundle_id:
        raise ContractError(
            "value-invalid",
            f"{where}.provenance.rolled_back_from names {bundle_id!r}, the bundle itself; a "
            f"rollback records which bundle was rolled back FROM, which is never this one",
        )

    return PolicyBundle(
        v=BUNDLE_VERSION, id=bundle_id,
        parent=None if parent is None else _frozen_map(parent),
        scope=scope, components=components, parameters=_frozen_map(parameters),
        requirements=requirements, fallback=fallback, provenance=provenance,
    )


# ---- CandidateProposal ----------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class CandidateProposal:
    """A falsifiable, bounded, data-only request to change a parent bundle's parameters.

    It carries its own counterevidence. That is not politeness: a proposal that lists only what
    supports it is a summary of a search for confirmation, and the attempts that contradict it
    are the ones that decide whether the evaluation is worth running. An empty counterevidence
    list is a claim -- "looked, found none" -- and it is recorded as one, never as an omission.
    """

    v: str
    id: str
    parent: types.MappingProxyType
    hypothesis: str
    falsification: str
    tradeoff: str
    scope: types.MappingProxyType
    diff: types.MappingProxyType
    evaluation: types.MappingProxyType
    evidence: tuple
    counterevidence: tuple
    rollback: types.MappingProxyType

    def to_payload(self):
        return {
            "v": self.v,
            "id": self.id,
            "parent": dict(self.parent),
            "hypothesis": self.hypothesis,
            "falsification": self.falsification,
            "tradeoff": self.tradeoff,
            "scope": {"project": self.scope["project"],
                      "task_classes": list(self.scope["task_classes"]),
                      "intended_uses": list(self.scope["intended_uses"])},
            "diff": dict(self.diff),
            "evaluation": {"endpoint": self.evaluation["endpoint"],
                           "partition": self.evaluation["partition"],
                           "manifest_ref": dict(self.evaluation["manifest_ref"])},
            "evidence": [dict(ref) for ref in self.evidence],
            "counterevidence": [dict(ref) for ref in self.counterevidence],
            "rollback": {"kind": self.rollback["kind"],
                         "bundle_ref": (None if self.rollback["bundle_ref"] is None
                                        else dict(self.rollback["bundle_ref"]))},
        }

    def sha(self):
        return _sha(_canonical(self.to_payload()))


def _evaluation(value, where):
    """The evaluation this candidate must pass, and the material it may be judged on."""
    payload = _closed(value, _EVALUATION_KEYS, where)
    endpoint = _label(payload["endpoint"], f"{where}.endpoint")
    partition = _label(payload["partition"], f"{where}.partition")
    _one_of(partition, EVIDENCE_PARTITIONS, f"{where}.partition")
    manifest = _pinned_ref(payload["manifest_ref"], f"{where}.manifest_ref")
    return _frozen_map({"endpoint": endpoint, "partition": partition,
                        "manifest_ref": _frozen_map(manifest)})


def _evidence(value, where, *, minimum):
    refs = _sequence(value, where, maximum=MAX_EVIDENCE_REFS, minimum=minimum)
    out = []
    seen = set()
    for index, item in enumerate(refs):
        ref = _pinned_ref(item, f"{where}[{index}]")
        if ref["id"] in seen:
            raise ContractError("duplicate-entry", f"{where} repeats {ref['id']!r}")
        seen.add(ref["id"])
        out.append(_frozen_map(ref))
    return tuple(out)


def parse_proposal(value, where="proposal"):
    """A candidate proposal, refused unless it is falsifiable, bounded and data-only."""
    payload, version = _declared_version(value, where)
    if version != CANDIDATE_VERSION:
        raise ContractError(
            "unknown-value",
            f"{where}.v is {version!r}; this parser reads {CANDIDATE_VERSION}",
        )
    payload = _closed(payload, _CANDIDATE_KEYS, where)
    proposal_id = _label(payload["id"], f"{where}.id")

    # A proposal is always a change TO something, and to exactly the bytes it was written
    # against: an unpinned parent would let the same candidate be applied to a bundle that had
    # moved underneath it, which is the change nobody reviewed.
    parent = _pinned_ref(payload["parent"], f"{where}.parent", version=BUNDLE_VERSION)

    hypothesis = _statement(payload["hypothesis"], f"{where}.hypothesis")
    falsification = _statement(payload["falsification"], f"{where}.falsification")
    tradeoff = _statement(payload["tradeoff"], f"{where}.tradeoff")
    if _alnum(hypothesis) == _alnum(proposal_id):
        raise ContractError(
            "value-invalid",
            f"{where}.hypothesis restates the id {proposal_id!r}; an id is a handle and never "
            f"the claim being made",
        )
    # `_alnum` is the same reduction the ban and the rubric check use, for the same reason:
    # comparing the strings as written would let re-punctuated copies count as different text.
    if _alnum(falsification) == _alnum(hypothesis):
        raise ContractError(
            "value-invalid",
            f"{where}.falsification is worded the same as {where}.hypothesis; restating a claim "
            f"names no observation that would refute it, and an unfalsifiable candidate cannot "
            f"be evaluated at all",
        )
    if _alnum(tradeoff) in (_alnum(hypothesis), _alnum(falsification)):
        raise ContractError(
            "value-invalid",
            f"{where}.tradeoff is worded the same as the hypothesis or the falsification; a "
            f"tradeoff names what is expected to get WORSE, which a restatement does not",
        )

    scope = _scope(payload["scope"], f"{where}.scope")
    diff = _parameters(payload["diff"], f"{where}.diff", minimum=1)
    evaluation = _evaluation(payload["evaluation"], f"{where}.evaluation")

    evidence = _evidence(payload["evidence"], f"{where}.evidence", minimum=MIN_EVIDENCE_REFS)
    counter = _evidence(payload["counterevidence"], f"{where}.counterevidence", minimum=0)
    both = sorted({ref["id"] for ref in evidence} & {ref["id"] for ref in counter})
    if both:
        raise ContractError(
            "duplicate-entry",
            f"{where} cites {', '.join(repr(b) for b in both)} as both evidence and "
            f"counterevidence; one attempt is one observation, and filing it on both sides "
            f"makes the count on each side mean nothing",
        )

    rollback = _fallback(payload["rollback"], f"{where}.rollback")

    return CandidateProposal(
        v=CANDIDATE_VERSION, id=proposal_id, parent=_frozen_map(parent), hypothesis=hypothesis,
        falsification=falsification, tradeoff=tradeoff, scope=scope,
        diff=_frozen_map(diff), evaluation=evaluation, evidence=evidence,
        counterevidence=counter, rollback=rollback,
    )
