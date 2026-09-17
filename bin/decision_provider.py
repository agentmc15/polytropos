#!/usr/bin/env python3
"""D12 -- one bounded request-to-result interface, and two providers that answer through it.

`bin/decision_contract.py` (D09/D10/D11) defines what a request, a result and a policy bundle
ARE and every refusal that makes one well formed. This module supplies the first two things that
can actually ANSWER a `DecisionRequest`:

  * `rules`  -- a deterministic, local computation over the request's own declared `state`. It
    ships with an EMPTY default rule table, on purpose: nothing in this kit has yet defined the
    domain-specific recovery heuristics that phases 4-5 (`D14`-`D19`) will eventually register,
    and inventing one here would be exactly the "candidate data changes the improvement
    procedure" mistake the plan forbids. A rule table is a caller-supplied mapping from a
    qualified question id to a callable; whatever it cannot decide, it abstains on -- per
    question where the question PERMITS abstention, and for the whole result where it cannot,
    because guessing at a mandatory answer is worse than saying so.
  * `replay` -- a lookup into a caller-selected, content-addressed store of PRIOR results. A
    cache hit reuses a prior answer without dispatching anything; a miss abstains. It never
    predicts a counterfactual and it never manufactures a fresh vendor observation out of an old
    one -- see "WHAT A REPLAY IS NOT" below.

Both are reached through the ONE public entry point, `evaluate(request, mode=..., ...)`, so a
caller that only knows "ask this provider" never has to know which implementation answered.
Both implementations return a PAYLOAD -- a plain JSON-shaped dict -- exactly like a live vendor
would, so the caller runs it through `decision_contract.parse_result(payload, request)` the same
way regardless of which provider produced it. This module also runs that same check on its own
output before returning, as a self-test; it is not a substitute for the caller's own check.

============================================================================================
 WHAT A REPLAY IS, AND WHAT IT IS NOT
============================================================================================
`record_result` persists a FRESH `DecisionResult` for later reuse, keyed by `replay_key`. The
shared plan pins what that identity must include: "project/provider eligibility, task/acceptance
version, complete state, alternatives, questions/rubrics, provider/model, policy and
calibrator." `DecisionRequest.sha()` already digests project/provider eligibility, task and
acceptance identity, complete state, alternatives and the question set in one number (D09's own
carry-forward note). What it does NOT pin is WHICH ONE of the eligible providers answered, which
model that provider used, which policy bundle was in force, or which calibrator -- those four
are this module's own parameters, folded on top of `request.sha()` in `replay_key`.

WHAT `request.sha()` ALSO PINS, WHICH THE PLAN DOES NOT LIST, AND WHY IT MATTERS.
`DecisionRequest.sha()` covers the WHOLE request, so it additionally folds in `correlation_id`,
`run`, `task` and `attempt`. Those four identify the OCCASION, not the decision situation. Two
requests identical in every respect the plan lists -- same state digest, same questions, same
alternatives, same eligibility -- therefore key DIFFERENTLY when only their correlation id
differs, and a correlation id is ordinarily fresh per call. So `replay` as keyed here hits only
when a caller re-asks with the very same request object, not when the same situation recurs.

That is conservative rather than wrong: a narrower key can only miss, never produce a false hit
on a different situation, so no stored answer is ever served for a decision it did not answer.
But a coordinator wiring this expecting a cache should know it will almost always abstain. Making
replay hit across recurring situations means keying on a NARROWER digest than `request.sha()`,
which is a change to what identity means and belongs to whoever owns that decision -- not to a
silent edit here. Recorded in the kit's NOTES for D20/D23.

A cache MISS is not a failure this module raises; it is `abstain`, because "nothing was ever
recorded for this exact identity" is itself unremarkable and non-fatal. A request whose
`eligibility.project` differs from what was recorded therefore produces a DIFFERENT
`request.sha()` and so a DIFFERENT key -- a cross-project request always misses, structurally,
never by a separate project check that could drift out of sync with the key.

A REPLAYED payload is never confused for a fresh one. `dispatched_provider`, `observed_provider`,
`dispatched_model` and `observed_model` are forced to `None` on the replayed payload -- nothing
was dispatched and nothing was freshly observed, which is the literal truth, not a label bolted
on afterward -- and so are `duration` and `usage`: a replay took no vendor time and spent no
vendor dollars, and GUARDRAILS is explicit that a missing cost is `null`, never `0`. `note`
carries a stable, grep-able prefix (`REPLAY_NOTE_PREFIX`) naming the correlation id of the
original call, so a caller reading only the payload -- not this module's source -- can still
tell a replay from a fresh answer. `requested_provider`/`requested_model` are the one pair
copied FORWARD from the original, because reporting what was originally asked for is different
from claiming something was freshly dispatched or observed now.

"Historical cost remains on its original record" is enforced by construction, not by convention:
`record_result` is CREATE-ONCE, mirroring `workflow_eval.write_manifest`'s own precedent exactly
-- the same identity recorded twice with the SAME content is a silent no-op, and recorded twice
with DIFFERENT content is refused loudly. A later call that produced a genuinely new usage number
for the same identity can never overwrite the first observation's evidence; it would have to be
filed under its own identity (a different model, a different bundle, a different calibrator) or
not at all. `_read_record` re-derives the stored content's digest on every read and refuses a
mismatch, the same chain-of-custody check `workflow_eval.read_manifest` performs on its own
manifests -- detection, never protection: anything running with the user's own privileges can
still rewrite the bytes on disk, but it cannot make this module serve the rewritten content as
though nothing happened.

============================================================================================
 THE STORE IS THE CALLER'S, NEVER THIS MODULE'S OWN DEFAULT
============================================================================================
Every function that touches storage takes an explicit `store_dir`. This module does not resolve
one on its own, does not read an environment variable, and does not know the runtime data
seam exists -- a caller that wants a real, per-user location resolves one itself and hands the
path in, exactly the "--memory-dir/--store-dir-style seam" the repository's own invariants
require. Every test here, and the verify command, therefore uses nothing but a temporary
directory it creates and destroys itself.

============================================================================================
 THE RUNNER PARAMETER, AND WHY IT IS ACCEPTED BUT NEVER CALLED
============================================================================================
`evaluate`, and both of the implementations underneath it, accept a `runner` keyword. Nothing in
this module invokes it: `rules` is a pure local computation and `replay` is a store lookup, and
NEITHER of those is a live dispatch. The parameter exists so a future live provider can share
this exact interface without a signature change, and so this module's own claim -- "replay makes
no call" -- has something concrete to prove itself against rather than being vacuously true of a
function that never mentions dispatch at all. `tests/test_decision_provider.py` proves it two
ways, deliberately paired: at runtime, by injecting a runner that RAISES the instant it is
invoked and asserting it was never touched; and structurally, by walking the implementation
function's own AST and asserting that among its (non-empty) set of calls, none names `runner`.

============================================================================================
 SAFETY CONTRACT
============================================================================================
Nothing here invokes a real `claude`/`codex`/`copilot`/`cursor`/`graphify` binary, starts a
process, reads a real home directory, or touches the network. The one form of I/O this module
performs -- reading and writing the replay store -- goes through `bin/safe_paths.py`'s confined
operations into the `store_dir` the CALLER supplied, never a hand-composed path. Every write is
either a fresh create (refused if the name is taken with different bytes) or a read; nothing is
ever deleted, appended to or replaced in place.

============================================================================================
 REUSE, NOT REINVENTION
============================================================================================
Every structural and value check on a request, a result, or an answer is `decision_contract`'s;
this module never repeats one. A provenance reference is `attempt_ledger.make_ref`/`read_ref`'s
shape, read by its own code. A decision's own latency is reported on the reserved
`decision-latency` basis and validated by `decision_contract`'s own duration parser, which itself
calls `attempt_history`'s reserved helper -- this module never reaches into `attempt_history` a
second time to do that job itself. The record persisted for replay is written the same
create-once, content-addressed way `workflow_eval.write_manifest` already writes the evaluation
store's own manifests -- a distinct store, under a name this module never spells, because that
one is owned by that module alone.
"""

import hashlib
import importlib.util
import json
import re
import time
import types
from pathlib import Path

#: The version of the STORED REPLAY RECORD's own envelope -- never `decision_contract`'s
#: `CONTRACT_VERSION`, `BUNDLE_VERSION` or `CANDIDATE_VERSION`, none of which this module owns
#: or may overload. Registered separately in `release_gate.VERSION_SOURCES`.
REPLAY_VERSION = "polytropos.decision-replay/1"

#: The two implementations `evaluate` dispatches to. Not a `decision_contract` vocabulary --
#: this module's own, closed here and nowhere else.
PROVIDER_MODES = ("rules", "replay")

#: Sub-directory of the caller's `store_dir` the replay records live under.
RECORD_DIR = "replay"

#: The stable, grep-able marker a replayed payload's `note` always starts with, followed by the
#: ORIGINAL call's correlation id. A caller -- or a test -- can tell a replay from a fresh answer
#: from the payload alone, without reading this module's source.
REPLAY_NOTE_PREFIX = "replay: reusing the answer recorded for correlation "

#: The note a replay cache MISS carries. Not a failure -- the whole point of a cache is that
#: "nothing recorded yet" is an ordinary, expected outcome, and it is reported as `abstain`,
#: never raised.
REPLAY_MISS_NOTE = ("replay: no stored record matches this request's identity, provider, model, "
                    "policy bundle and calibrator")

#: The two ways the rules provider abstains on the WHOLE result rather than answering it.
RULES_ABSTAIN_EMPTY_NOTE = ("rules: no registered rule decided any question in this request; "
                            "abstaining under semantic uncertainty rather than guessing")
RULES_ABSTAIN_BLOCKED_NOTE = ("rules: a question whose spec forbids abstention could not be "
                              "decided by any registered rule; abstaining for the whole result "
                              "instead of answering some questions and guessing at one that "
                              "must not be skipped")

#: The default rule table: empty. See the module docstring for why that is deliberate.
DEFAULT_RULES = types.MappingProxyType({})

_SHA_RE = re.compile(r"\A[0-9a-f]{64}\Z")

# ---- sibling loaders (bin/ is not a package) ----------------------------------------------------

_MODS = {}


def _sibling(name):
    if name not in _MODS:
        path = Path(__file__).resolve().parent / f"{name}.py"
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _MODS[name] = mod
    return _MODS[name]


def _contract():
    return _sibling("decision_contract")


def _al():
    return _sibling("attempt_ledger")


def _sp():
    return _sibling("safe_paths")


def _refuse(code, message):
    """One refusal, in the contract's own vocabulary rather than a second one beside it."""
    return _contract().ContractError(code, message)


# ---- canonical form, local to this module's own store (never the contract's private one) --------

def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---- shared guards -------------------------------------------------------------------------------

def _require_request(request, where):
    if not isinstance(request, _contract().DecisionRequest):
        raise _refuse("wrong-type",
                      f"{where} needs the parsed DecisionRequest this answers, not a payload")


def _require_provider(request, provider, where):
    if provider not in request.eligibility["providers"]:
        raise _refuse(
            "unknown-value",
            f"{where}: {provider!r} is not one of this request's eligible providers "
            f"{list(request.eligibility['providers'])}; a provider may only answer a request "
            f"that named it eligible",
        )


def _digest_or_none(value, where):
    if value is None:
        return None
    if not isinstance(value, str) or not _SHA_RE.match(value):
        raise _refuse("value-invalid",
                      f"{where} is not a lowercase sha256 hex digest: {value!r}")
    return value


def _calibrator_or_none(value, where):
    """A calibrator identity that PINS content, or `None`.

    `attempt_ledger.read_ref` alone permits a digest-free pointer -- honest for an event's
    provenance, where a caller may not know one. A replay identity is the opposite case: a
    calibrator reference that does not pin the exact bytes it names cannot notice the calibrator
    changing underneath it, so two different calibrators sharing one id would silently collapse
    onto the same replay key. This re-checks that locally rather than reaching into
    `decision_contract`'s private `_pinned_ref`, which is not this module's to call.
    """
    if value is None:
        return None
    read = _al().read_ref(value)
    if read is None or read["sha"] is None or read["v"] is None:
        raise _refuse(
            "not-a-reference",
            f"{where} must be a reference that pins an id, a digest and a version, or null; "
            f"got {value!r}",
        )
    return read


def _abstain_payload(request, *, provider, model, note):
    """The shape every abstention this module returns shares: no values, no fresh cost."""
    return {
        "v": _contract().CONTRACT_VERSION, "correlation_id": request.correlation_id,
        "state_sha": request.state_sha, "questions_sha": request.questions_sha,
        "status": "abstain", "answers": {}, "recommended": None, "evidence_refs": [],
        "requested_provider": provider, "dispatched_provider": None, "observed_provider": None,
        "requested_model": model, "dispatched_model": None, "observed_model": None,
        "provider_contract_v": None, "duration": None, "usage": None, "note": note,
    }


# ---- the replay identity -------------------------------------------------------------------------

def replay_key(request, *, provider, model=None, bundle_sha=None, calibrator_ref=None):
    """The identity a fresh record and a later lookup must agree on to be the same call.

    `request.sha()` already covers project/provider eligibility, task and acceptance identity,
    complete state, alternatives and the question set. Layered on top, exactly as the shared
    plan pins: WHICH of the eligible providers answered, which model it used, which policy
    bundle's digest was in force (`None` for the legacy default), and which calibrator (`None`
    for none). Two calls that agree on all of this are the same call; any difference is a
    different one, keyed separately.

    `request.sha()` ALSO folds in `correlation_id`, `run`, `task` and `attempt`, which identify
    the occasion rather than the situation -- so this key distinguishes two otherwise identical
    decision situations asked under different correlation ids. See the module docstring: that is
    conservative, never a false hit, but it means replay rarely hits in practice.
    """
    _require_request(request, "replay key")
    _require_provider(request, provider, "replay key")
    bundle_sha = _digest_or_none(bundle_sha, "replay key bundle_sha")
    calibrator = _calibrator_or_none(calibrator_ref, "replay key calibrator_ref")
    payload = {
        "request_sha": request.sha(), "provider": provider, "model": model,
        "bundle_sha": bundle_sha, "calibrator": calibrator,
    }
    return _sha(_canonical(payload))


# ---- storage: one owner, create-once, never rewritten -------------------------------------------

def _root(store_dir):
    root = Path(store_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _rel(key):
    safe = _sp().validate_id(key, "replay key")
    return f"{RECORD_DIR}/{safe}.json"


def record_result(store_dir, request, result, *, provider, model=None, bundle_sha=None,
                  calibrator_ref=None):
    """Persist a FRESH `DecisionResult` for later replay. The ONLY function that writes here.

    Create-once: the same identity recorded twice with identical content is a harmless no-op
    (the FIRST bytes are kept, so their evidence is the historical one); recorded twice with
    DIFFERENT content is refused loudly, because a content-addressed identity that now points at
    different bytes is either a rewrite or a collision, and this module treats both the same way
    -- refuse, and touch nothing. That refusal is what makes "zero new calls must not rewrite old
    resource evidence" true by construction rather than by discipline.

    Refuses a result that is ITSELF a replay (`note` already carries `REPLAY_NOTE_PREFIX`):
    recording a replayed answer as though it were freshly observed would launder a cache hit
    into a new historical observation, which is exactly the thing this module exists to prevent.
    """
    _require_request(request, "record result")
    contract = _contract()
    if not isinstance(result, contract.DecisionResult):
        raise _refuse("wrong-type",
                      "record result needs the parsed DecisionResult, not a payload")
    if result.correlation_id != request.correlation_id:
        raise _refuse("correlation-mismatch",
                      "record result: the result and the request are not correlated")
    _require_provider(request, provider, "record result")
    if result.requested_provider != provider:
        raise _refuse(
            "value-invalid",
            f"record result: provider is {provider!r} but the result's own requested_provider "
            f"is {result.requested_provider!r}; the identity a replay is filed under must be "
            f"the identity the result itself claims",
        )
    if result.requested_model != model:
        raise _refuse(
            "value-invalid",
            f"record result: model is {model!r} but the result's own requested_model is "
            f"{result.requested_model!r}",
        )
    if result.note is not None and result.note.startswith(REPLAY_NOTE_PREFIX):
        raise _refuse(
            "value-invalid",
            "record result: this result is itself a replayed answer, disclosed by its own "
            "note; a replay is not a fresh vendor observation and recording it as one would "
            "launder a cache hit into a new historical observation",
        )
    bundle_sha = _digest_or_none(bundle_sha, "record result bundle_sha")
    calibrator = _calibrator_or_none(calibrator_ref, "record result calibrator_ref")
    key = replay_key(request, provider=provider, model=model, bundle_sha=bundle_sha,
                     calibrator_ref=calibrator_ref)
    content = {
        "request_sha": request.sha(), "project": request.eligibility["project"],
        "provider": provider, "model": model, "bundle_sha": bundle_sha,
        "calibrator": calibrator, "correlation_id": request.correlation_id,
        "result": result.to_payload(),
    }
    sha = _sha(_canonical(content))
    blob = {"v": REPLAY_VERSION, "key": key, "sha": sha, "content": content}
    body = (json.dumps(blob, indent=2, sort_keys=True) + "\n").encode("utf-8")
    root = _root(store_dir)
    rel = _rel(key)
    sp = _sp()
    try:
        sp.confined_create_bytes(root, rel, body, what="decision replay record")
    except sp.SafePathExists:
        raw = sp.confined_read_bytes(root, rel, what="decision replay record")
        existing = json.loads(raw.decode("utf-8"))
        if _canonical(existing.get("content")) != _canonical(content):
            raise _refuse(
                "value-invalid",
                "a decision replay record already exists for this identity with DIFFERENT "
                "content; historical cost stays on the record that first observed it, and a "
                "fresh call under the same identity never rewrites it. Nothing was overwritten",
            ) from None
    return key


def _read_record(store_dir, key):
    """The stored content for `key`, or `None` for an honest miss. Never a silent tamper."""
    root = Path(store_dir)
    sp = _sp()
    raw = (sp.confined_read_bytes(root, _rel(key), what="decision replay record",
                                  missing_ok=True) if root.is_dir() else None)
    if raw is None:
        return None
    blob = json.loads(raw.decode("utf-8"))
    if blob.get("v") != REPLAY_VERSION:
        raise _refuse("unknown-value",
                      f"a decision replay record under {key!r} is not a {REPLAY_VERSION} record")
    content = blob.get("content")
    sha = _sha(_canonical(content))
    if sha != blob.get("sha") or blob.get("key") != key:
        raise _refuse(
            "value-invalid",
            f"the decision replay record under {key!r} does not match its own digest; it has "
            f"been rewritten since it was recorded",
        )
    return content


# ---- the two implementations ---------------------------------------------------------------------

def _ruleset(rules):
    if not isinstance(rules, (dict, types.MappingProxyType)):
        raise _refuse("wrong-type",
                      "rules must be a mapping of a qualified question id to a callable")
    for qid, fn in rules.items():
        if not isinstance(qid, str) or not callable(fn):
            raise _refuse(
                "wrong-type",
                "a rules entry must map a qualified question id (a string) to a callable "
                "(state, spec) -> an outcome in spec.outcomes, or None to abstain on it",
            )
    return rules


def _evaluate_rules(request, *, provider, rules=None, runner=None):
    """The rules implementation. Deterministic, local, and never invokes `runner` (see the
    module docstring's "THE RUNNER PARAMETER" section for why the parameter exists at all).

    Each question is decided independently by looking up its qualified id in `rules` (the empty
    `DEFAULT_RULES` when the caller supplies none) and calling it with `(state, spec)`. A rule
    that returns `None` means "I cannot tell", and that question is recorded abstained; one that
    returns a value outside `spec.outcomes` is a defect in the RULE, refused rather than passed
    through, because inventing a category is exactly what `decision_contract` already refuses a
    vendor for doing.

    The whole result abstains -- rather than answering some questions and guessing at one it
    must not skip -- whenever EITHER nothing was decided at all (the empty default table, or a
    caller's table that matched nothing here) OR at least one question whose spec forbids
    abstention could not be decided. Otherwise it is `ok`, with a real outcome for every question
    a rule decided and an explicit per-question abstention for every one it did not (legal only
    because that question's own spec permits it) -- fine-grained "semantic uncertainty abstains"
    rather than an all-or-nothing answer.

    `recommended` is always `None`. Choosing among alternatives is `decision_policy`'s job
    (D13); a rules provider states what it believes about the questions it was asked, never
    which action follows from that belief.
    """
    _require_request(request, "evaluate rules")
    _require_provider(request, provider, "evaluate rules")
    ruleset = DEFAULT_RULES if rules is None else _ruleset(rules)
    state = dict(request.state)
    answers = {}
    blocked = False
    decided_any = False
    started = time.perf_counter()
    for spec in request.questions:
        fn = ruleset.get(spec.qualified_id)
        outcome = None if fn is None else fn(state, spec)
        if outcome is not None:
            if outcome not in spec.outcomes:
                raise _refuse(
                    "unknown-value",
                    f"the rule registered for {spec.qualified_id!r} returned {outcome!r}, "
                    f"which is not one of this question's own outcomes {list(spec.outcomes)}",
                )
            decided_any = True
            answers[spec.qualified_id] = {
                "outcome": outcome, "abstained": False, "raw": None, "calibrated": None,
                "vendor_confidence": None,
            }
        else:
            if spec.abstention == "forbidden":
                blocked = True
            answers[spec.qualified_id] = {
                "outcome": None, "abstained": True, "raw": None, "calibrated": None,
                "vendor_confidence": None,
            }
    elapsed = time.perf_counter() - started
    duration = {"basis": _contract().DECISION_DURATION_BASIS, "seconds": elapsed,
               "source": provider}

    if not decided_any:
        payload = _abstain_payload(request, provider=provider, model=None,
                                   note=RULES_ABSTAIN_EMPTY_NOTE)
        payload["duration"] = duration
    elif blocked:
        payload = _abstain_payload(request, provider=provider, model=None,
                                   note=RULES_ABSTAIN_BLOCKED_NOTE)
        payload["duration"] = duration
    else:
        payload = {
            "v": _contract().CONTRACT_VERSION, "correlation_id": request.correlation_id,
            "state_sha": request.state_sha, "questions_sha": request.questions_sha,
            "status": "ok", "answers": answers, "recommended": None, "evidence_refs": [],
            "requested_provider": provider, "dispatched_provider": provider,
            "observed_provider": None, "requested_model": None, "dispatched_model": None,
            "observed_model": None, "provider_contract_v": None,
            "duration": duration, "usage": None, "note": None,
        }
    _contract().parse_result(payload, request)
    return payload


def _evaluate_replay(request, store_dir, *, provider, model=None, runner=None, bundle_sha=None,
                     calibrator_ref=None):
    """The replay implementation. Looks up `replay_key(...)`; NEVER dispatches anything.

    A miss is `abstain` with `REPLAY_MISS_NOTE`. A hit rewrites only the fields that must always
    describe the CURRENT call (`correlation_id`, `state_sha`, `questions_sha` -- copied from
    `request`, not the stored original) and the fields that must always describe NOTHING having
    just happened (`dispatched_provider`, `observed_provider`, `dispatched_model`,
    `observed_model`, `duration`, `usage` -- all forced to `None`), then stamps `note` with
    `REPLAY_NOTE_PREFIX` and the original call's correlation id. Everything else -- `status`,
    `answers`, `recommended`, `evidence_refs`, `requested_provider`, `requested_model`,
    `provider_contract_v` -- is the original observation, unmodified: a replay reuses what was
    once seen, and improves on nothing.
    """
    _require_request(request, "evaluate replay")
    _require_provider(request, provider, "evaluate replay")
    bundle_sha = _digest_or_none(bundle_sha, "evaluate replay bundle_sha")
    calibrator = _calibrator_or_none(calibrator_ref, "evaluate replay calibrator_ref")
    key = replay_key(request, provider=provider, model=model, bundle_sha=bundle_sha,
                     calibrator_ref=calibrator_ref)
    content = _read_record(store_dir, key)
    if content is None:
        payload = _abstain_payload(request, provider=provider, model=model,
                                   note=REPLAY_MISS_NOTE)
    else:
        original = content["result"]
        payload = dict(original)
        payload["correlation_id"] = request.correlation_id
        payload["state_sha"] = request.state_sha
        payload["questions_sha"] = request.questions_sha
        payload["dispatched_provider"] = None
        payload["observed_provider"] = None
        payload["dispatched_model"] = None
        payload["observed_model"] = None
        payload["duration"] = None
        payload["usage"] = None
        payload["note"] = f"{REPLAY_NOTE_PREFIX}{content['correlation_id']!r}"
    _contract().parse_result(payload, request)
    return payload


# ---- the one public interface --------------------------------------------------------------------

def evaluate(request, *, mode, provider, model=None, runner=None, rules=None, store_dir=None,
            bundle_sha=None, calibrator_ref=None):
    """The single bounded request-to-result interface. Returns a PAYLOAD, not a parsed object --
    exactly what a live vendor would hand back -- so a caller runs it through
    `decision_contract.parse_result(payload, request)` the same way regardless of `mode`.

    `mode='rules'` reaches `_evaluate_rules`; `mode='replay'` reaches `_evaluate_replay` and
    requires `store_dir`. Any other `mode` is refused outright -- there is no third
    implementation here, and this function does not silently fall through to one.
    """
    if mode == "rules":
        return _evaluate_rules(request, provider=provider, rules=rules, runner=runner)
    if mode == "replay":
        if store_dir is None:
            raise _refuse(
                "missing-field",
                "evaluate: mode 'replay' needs store_dir, the caller-selected directory its "
                "records live under",
            )
        return _evaluate_replay(request, store_dir, provider=provider, model=model,
                                runner=runner, bundle_sha=bundle_sha,
                                calibrator_ref=calibrator_ref)
    raise _refuse("unknown-value",
                  f"evaluate: mode is {mode!r}; the vocabulary is {PROVIDER_MODES}")
