#!/usr/bin/env python3
"""The prediction-time join: what was knowable when a decision was taken, what was observed
afterwards, and which of the two every fact in the row belongs to.

WHAT WAS WRONG. A decision, the attempts that followed it and the grading of those attempts are
three records that never met. The decision lives in a `DecisionRecord`; the attempts live in the
attempt ledger and reach a reader through `bin/attempt_history.py`'s projection; the grading
lives in a `bin/workflow_eval.py` results envelope. Nothing put them in one row, so nothing could
say what a decision was TAKEN ON versus what only became true later -- and a single row mixing
the two is how an evaluation reports a result it could not have predicted.

WHAT THIS IS. A read-only join, one row per decision, with four rules that do the work:

  * EVERY FACT IS PLACED IN TIME AGAINST THE PREDICTION INSTANT (`FACT_PLACEMENTS`). Only a fact
    at or before it is a feature; a fact after it is outcome evidence, kept and visible under
    its own name, never a feature. A fact whose timestamp is missing, malformed or zoneless is
    `unknown-time` -- unplaceable, and so neither. When nobody recorded the prediction instant,
    NOTHING is a feature, because "before" has no meaning without it.
  * EVERY QUESTION CARRIES ITS TARGET AND ITS LABEL PROVENANCE. A target says which observable
    resolves the question and how that observable's values map into the question's own outcomes.
    A label carries every observation behind it -- source, reference, observed value, mapped
    value. Two sources that disagree make the label `disputed` and BOTH are kept; this module
    never picks a winner, and a question nobody declared a target for is `missing`, not absent.
  * WHAT IS NOT YET KNOWN IS CENSORED, NOT DROPPED (`CENSORING_REASONS`). An open attempt, an
    attempt whose outcome is unknown, a skipped or excluded trial, an observation window still
    open, and a decision that was REFUSED and therefore has no record at all, are all rows in
    the join with their reason attached.
  * AN ACTION THAT WAS NOT TAKEN HAS NO OUTCOME. The outcome slot of an alternative is filled
    only for the action actually taken; every other alternative carries `UNTRIED_ACTION_NOTE`
    and a null. An on-policy record cannot reveal what an untried action would have done, and
    there is no field here that could hold one. The row's own `actions.outcome` is scoped the
    same way: it describes what followed the action in `actions.taken`, so a decision that
    took none -- a refusal, or a row with no record -- leaves it null and says why
    (`NO_ACTION_OUTCOME_NOTE`). The fact that followed stays in `outcome_evidence`, where it
    is evidence of what happened next and not of what the decision produced.

WHAT IT REFUSES. It writes nothing, anywhere: it opens no file, takes no path, and is handed
projections that their own owners read. It never totals two durations measured by different
clocks -- `duration_by_basis` keeps them apart, as `attempt_history.duration_totals` does. It
carries no causal claim: `_assert_no_causal_claim` sweeps every row it emits for a key spelled
like causation, so a later reporting task extending this module cannot quietly add one. And it
does not carry the provider's free-text note (`NOTE_WITHHELD`).

ONE AUTHORITY PER CONCERN. Four siblings are loaded for their VOCABULARY and nothing else --
`bin/decision_contract.py` for the contract version and its refusal codes, `bin/decision_policy.py`
for the refusal reasons a selection may carry, `bin/attempt_history.py` for the projection's own
record fields and duration bases, and `bin/workflow_eval.py` for the version its envelope is
stamped with. `tests/test_decision_eval.py` walks this file's AST and pins exactly which names
are reached on each, so none of them can turn into a call.
"""

import datetime
import importlib.util
import re
import types
from pathlib import Path

#: This join's own schema. Not the decision contract's, not the evaluation envelope's: a row
#: here is a THIRD object, assembled from both, and a reader that fetched one needs to know
#: which field names apply to IT. Registered in `release_gate.VERSION_SOURCES` in its own right.
JOIN_VERSION = "polytropos.decision-join/1"

#: Where a fact sits relative to the instant the decision was taken. `unknown-time` is a third
#: answer and not a synonym for either: a fact nobody timestamped is unplaceable, and calling it
#: "before" is how future information becomes a feature.
FACT_PLACEMENTS = ("at-or-before-prediction", "after-prediction", "unknown-time")

#: What a question's label can be. `disputed` is not a failure to label -- it is the label,
#: recording that two authorities looked at the same thing and said different words.
LABEL_STATUSES = ("resolved", "disputed", "missing", "censored")

#: Who produced an observation. Closed, because a report counts these and an unlabelled source
#: would tally as evidence of the same weight as a graded one.
LABEL_SOURCES = ("tests-oracle", "review-verdict", "kit-acceptance", "human-adjudication",
                 "attempt-outcome")

#: The subset of `LABEL_SOURCES` that is a person. Kept apart because the plan's rule is that
#: judge opinion is not ground truth: a human verdict and an oracle verdict that disagree are a
#: disagreement to report, never a vote to settle.
HUMAN_LABEL_SOURCES = ("human-adjudication",)

#: Which observable a question's target is resolved against. `attempt-outcome` is the attempt
#: projection's own `result`; `trial-outcome` is an evaluation trial's grading. They are
#: separate observables with separate value spaces, and a target names exactly one.
TARGET_OBSERVABLES = ("attempt-outcome", "trial-outcome")

#: The values a `trial-outcome` observation can take, normalised across the four graders an
#: evaluation trial carries. `accepted` and `solved` are DIFFERENT observations -- an acceptance
#: is somebody saying yes, a solve is the tests oracle passing -- and a target that maps both
#: into one question's outcomes is what makes their disagreement visible.
TRIAL_OUTCOMES = ("solved", "not-solved", "accepted", "not-accepted")

#: Why a row's label is not yet knowable. Every one of these is derived from a joined fact, not
#: supplied by the caller: there is deliberately no seam through which a row can be declared
#: censored without the evidence that makes it so.
CENSORING_REASONS = ("attempt-open", "outcome-unknown", "outcome-not-graded",
                     "attempt-budget-stop", "trial-skipped", "trial-excluded",
                     "observation-window-open", "refusal-has-no-record",
                     "decision-record-absent")

#: Why a row could not be joined completely. An unresolved row STAYS in the join carrying one of
#: these; dropping it would quietly improve every rate computed downstream.
UNRESOLVED_REASONS = ("refusal-has-no-record", "decision-record-absent",
                      "prediction-time-unknown", "no-target-declared")

#: How two facts may be related. There is deliberately no causal member, and `RELATIONS` is the
#: whole vocabulary: ordering is all a join can establish from a log. Only `followed` has a
#: producer at this revision -- the other two are declared so a later pairing has a word that
#: is already an ordering, rather than reaching for one that is not.
RELATIONS = ("preceded", "co-occurred", "followed")

#: Failure classes the ledger determines from trusted events. They are FACTS about the
#: environment, and they are exactly the classes the plan says must never trigger an escalation
#: from a semantic guess. Held here as the subset worth flagging, never re-derived: the class
#: itself is read from the attempt record and from nowhere else.
DETERMINISTIC_FAILURE_CLASSES = ("infrastructure", "auth", "config", "permission")

#: Attempt results that show the task got through.
RECOVERED_RESULTS = ("pass", "retry-pass", "escalated-pass")

#: Attempt results that show it did not.
FAILED_RESULTS = ("verify-failed", "dispatch-failed", "blocked")

#: Attempt results that are not an outcome at all yet -> the censoring reason each one means.
CENSORING_BY_RESULT = types.MappingProxyType({
    "open": "attempt-open",
    "unknown": "outcome-unknown",
    "dispatched": "outcome-not-graded",
    "budget-stop": "attempt-budget-stop",
})

UNTRIED_ACTION_NOTE = (
    "not taken: an on-policy record shows what happened after the action that WAS taken and "
    "reveals nothing about the outcome of one that was not. This row carries no field that "
    "could hold an untried action's outcome"
)

NO_ACTION_OUTCOME_NOTE = (
    "no action was taken: this slot describes what followed the action named in `taken`, and a "
    "decision that refused -- or that left no record of a selection at all -- took none, so "
    "there is nothing here for it to describe. What happened afterwards is still in the row, "
    "under `outcome_evidence`, as evidence of what followed rather than as this decision's "
    "own outcome"
)

NO_CAUSAL_CLAIM = (
    "co-occurrence in time only: a later attempt that passed is not evidence that the "
    "intervention recorded before it is why, and a recovery that succeeded does not show the "
    "diagnosis behind it was correct. This block places two facts in order and carries no "
    "field that could assert one caused the other"
)

INFRASTRUCTURE_FACT_NOTE = (
    "read from the attempt event's own failure class and from nowhere else: an environment, "
    "auth, config or permission failure is a deterministic fact about the host, and it is "
    "evidence about neither the action taken nor the model that took it"
)

NOTE_WITHHELD = (
    "the provider's free-text note is not carried into a joined row: it is provider-controlled "
    "text, bounded by the decision contract but never passed through bin/redact.py, and a join "
    "is a reporting surface"
)

DURATIONS_SEPARATE = (
    "durations are grouped by basis and never summed across bases: a decision's own latency and "
    "a process's wall clock are two quantities measured by two clocks"
)

#: Bounds. A join is assembled from records that are already bounded by their own owners; these
#: stop a caller handing over an unbounded collection, not a malicious payload.
MAX_TARGETS = 32
MAX_MAPPING_ENTRIES = 32
MAX_HISTORY_RECORDS = 512
MAX_REFUSAL_REASONS = 16
MAX_ROWS = 4096

#: Keys and values spelled like an assertion that one fact caused another, reduced the way
#: `decision_contract._is_banned_key` reduces a banned field name so punctuation cannot dress
#: one up. The join establishes ordering; nothing here may claim more than that.
CAUSAL_TOKENS = ("caused", "causedby", "causes", "causal", "because", "proves", "proven",
                 "provesthat", "dueto", "therefore", "responsiblefor", "explains", "attributedto")


# ---- sibling loaders (bin/ is not a package) -------------------------------------------------

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
    """`bin/decision_contract.py` -- the version every decision object is stamped with, and the
    refusal vocabulary this module raises in rather than inventing a second one."""
    return _sibling("decision_contract")


def _dp():
    """`bin/decision_policy.py`, loaded for its REFUSAL VOCABULARY only.

    A decision that refused to act has no record to join -- the selection that refused names
    its own reasons, and those reasons are that module's to declare. This module reads the
    tuple and never reaches a function: a join makes no selection, and a second module deciding
    what a refusal may say would be a second authority over the same vocabulary.
    """
    return _sibling("decision_policy")


def _ah():
    """`bin/attempt_history.py`, loaded for its RECORD FIELDS and DURATION BASES only.

    That module owns what an attempt projection IS. This one reads the projection and so must
    agree with it about which field names exist and which duration bases are separate facts --
    by reading them, never by keeping a copy that drifts.
    """
    return _sibling("attempt_history")


def _we():
    """`bin/workflow_eval.py`, loaded for its ENVELOPE VERSION only.

    The evaluation workbench is the one writer of benchmark results. This module reads an
    envelope it was handed and must be able to say "this is not a version of the envelope I
    know" rather than reading fields out of an unversioned object. Reaching any other name on
    it would make this a second writer, which is exactly what the plan forbids.
    """
    return _sibling("workflow_eval")


def _refuse(code, message):
    """One refusal, in the contract's own vocabulary rather than a second one beside it."""
    return _contract().ContractError(code, message)


# ---- reading what someone else validated ----------------------------------------------------

def _payload_of(obj, version, where):
    """A PARSED decision object -> its payload, checked for the version it claims to be.

    Deliberately refuses a raw dict. `bin/decision_contract.py` is the validator for every one
    of these objects, and a join that accepted a payload directly would be validating decision
    shapes a second time, in a module whose job is to read them. The narrow duck type -- an
    object carrying `to_payload()` -- is on purpose too: `bin/` is not a package, two loaders of
    the contract produce two unrelated sets of classes, and an `isinstance` check here would
    refuse a perfectly valid object for having been parsed by the other copy.
    """
    maker = getattr(obj, "to_payload", None)
    if not callable(maker) or isinstance(obj, (dict, types.MappingProxyType)):
        raise _refuse(
            "wrong-type",
            f"{where} must be an object already parsed by bin/decision_contract.py, not a raw "
            f"payload: this module reads what that validator produced and is not a second "
            f"validator of the same shapes")
    payload = maker()
    if not isinstance(payload, dict):
        raise _refuse("wrong-type", f"{where} did not produce a payload object")
    if payload.get("v") != version:
        raise _refuse("unknown-value",
                      f"{where} is stamped {payload.get('v')!r}; this join reads {version!r}")
    return payload


def _copy(value):
    """A deep copy of JSON-shaped data. Every fact lifted out of an input lands in a row through
    this, so that mutating a returned row can never reach back into the caller's records."""
    if isinstance(value, (dict, types.MappingProxyType)):
        return {key: _copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_copy(item) for item in value]
    return value


def _alnum(text):
    return re.sub(r"[^a-z0-9]+", "", text.lower())


_CAUSAL_ALNUM = frozenset(_alnum(token) for token in CAUSAL_TOKENS)


def _is_causal_key(key):
    if not isinstance(key, str):
        return False
    if _alnum(key) in _CAUSAL_ALNUM:
        return True
    return any(_alnum(part) in _CAUSAL_ALNUM for part in key.split("."))


def assert_no_causal_claim(value, where="the joined row"):
    """Refuse a structure carrying a key spelled like "this caused that".

    Every row this module emits is swept, which is nearly free today because no code path here
    can produce such a key. Its work is forward: `bin/decision_eval.py` is extended by the
    reporting tasks that come after this one, and a `caused_by` added to a recovery block would
    turn an ordering into a finding. A successful recovery after a diagnosis is co-occurrence;
    the arrow is a claim, and this module is not entitled to make it.
    """
    hits = []
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, (dict, types.MappingProxyType)):
            for key, sub in item.items():
                if _is_causal_key(key):
                    hits.append(key)
                stack.append(sub)
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
    if hits:
        raise _refuse(
            "authority-field",
            f"{where} carries {', '.join(repr(h) for h in sorted(set(hits)))}. {NO_CAUSAL_CLAIM}")
    return value


# ---- placing a fact in time ------------------------------------------------------------------

def _instant(value):
    """An ISO-8601 timestamp -> comparable seconds, or None for "names no instant".

    A zoneless stamp returns None on purpose. Every producer joined here writes UTC with a
    trailing `Z` (`attempt_ledger._now`, `kit_contract`'s two stamps), so a naive one did not
    come from them, and reading it as local time would silently place a fact on one side of the
    prediction instant on the strength of the reader's own machine.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None
    return moment.timestamp()


def placement(ts, prediction_at):
    """Where `ts` sits relative to the prediction instant -> one of `FACT_PLACEMENTS`.

    THE future-exclusion primitive. Both sides must name an instant: with no prediction time
    there is no "before", so every fact is `unknown-time` and the row has no features at all.
    """
    at = _instant(ts)
    predicted = _instant(prediction_at)
    if at is None or predicted is None:
        return "unknown-time"
    return "at-or-before-prediction" if at <= predicted else "after-prediction"


# ---- the prediction target -------------------------------------------------------------------

def target(question, *, observable, mapping, note=""):
    """What a question is asking about the world, and how the world's answer becomes its own.

    `mapping` is the whole of the definition: an observable speaks its own vocabulary (an
    attempt `result`, a trial grading) and a question has its own permitted outcomes, and the
    translation between them is a decision somebody must write down BEFORE the labels are read.
    An observed value with no entry is not translated by guessing; it stays visible as an
    unmapped observation and the label says so.
    """
    if not isinstance(question, str) or not question.strip():
        raise _refuse("wrong-type", "a target names the question it resolves, as `id@version`")
    if observable not in TARGET_OBSERVABLES:
        raise _refuse("unknown-value",
                      f"a target's observable is {observable!r}; the observables a join can "
                      f"resolve against are {', '.join(TARGET_OBSERVABLES)}")
    if not isinstance(mapping, (dict, types.MappingProxyType)) or not mapping:
        raise _refuse("missing-field",
                      f"the target for {question!r} maps no observed value to an outcome; a "
                      f"target with no mapping defines no prediction")
    if len(mapping) > MAX_MAPPING_ENTRIES:
        raise _refuse("bounds-exceeded",
                      f"the target for {question!r} maps {len(mapping)} values; the ceiling is "
                      f"{MAX_MAPPING_ENTRIES}")
    pairs = {}
    for observed, outcome in mapping.items():
        if not isinstance(observed, str) or not observed:
            raise _refuse("wrong-type", f"the target for {question!r} maps a non-string value")
        if not isinstance(outcome, str) or not outcome:
            raise _refuse("wrong-type",
                          f"the target for {question!r} maps {observed!r} to a non-string outcome")
        pairs[observed] = outcome
    if not isinstance(note, str):
        raise _refuse("wrong-type", "a target's note is text")
    return {"question": question, "observable": observable,
            "mapping": dict(sorted(pairs.items())), "note": note}


def _targets(targets, request):
    """Declared targets, checked against the questions the request actually asked."""
    if not isinstance(targets, (list, tuple)):
        raise _refuse("wrong-type", "the targets must be a list")
    if len(targets) > MAX_TARGETS:
        raise _refuse("bounds-exceeded",
                      f"{len(targets)} targets were declared; the ceiling is {MAX_TARGETS}")
    specs = {f"{q['id']}@{q['version']}": q for q in request["questions"]}
    out = {}
    for item in targets:
        if not isinstance(item, (dict, types.MappingProxyType)):
            raise _refuse("wrong-type", "a target is the object `target()` returns")
        missing = sorted({"question", "observable", "mapping"} - set(item))
        if missing:
            raise _refuse("missing-field",
                          f"a target is missing {', '.join(repr(m) for m in missing)}; build it "
                          f"with target()")
        question = item["question"]
        spec = specs.get(question)
        if spec is None:
            raise _refuse("unknown-question",
                          f"a target was declared for {question!r}, which this request never "
                          f"asked; the request's questions are {', '.join(sorted(specs))}")
        if question in out:
            raise _refuse("duplicate-entry", f"{question!r} carries two targets")
        outcomes = tuple(spec["outcomes"])
        for observed, outcome in item["mapping"].items():
            if outcome not in outcomes:
                raise _refuse(
                    "unknown-value",
                    f"the target for {question!r} maps {observed!r} to {outcome!r}, which is "
                    f"not one of that question's outcomes {list(outcomes)}")
        out[question] = _copy(dict(item))
    return out


# ---- observations ----------------------------------------------------------------------------

def _history_record(rec, where):
    """One `attempt_history` projection record, checked against that module's own field names."""
    if not isinstance(rec, (dict, types.MappingProxyType)):
        raise _refuse("wrong-type", f"{where} must be an attempt history record")
    fields = set(_ah().RECORD_FIELDS)
    extra = sorted(set(rec) - fields)
    if extra:
        raise _refuse("unknown-field",
                      f"{where} carries {', '.join(repr(e) for e in extra)}, which "
                      f"bin/attempt_history.py does not project; this join reads that "
                      f"projection and not a shape assembled beside it")
    if "result" not in rec:
        raise _refuse("missing-field", f"{where} records no result")
    return rec


def _duration_entry(value, where):
    """A duration block, checked against the bases `attempt_history` declares separate."""
    if value is None:
        return None
    if not isinstance(value, (dict, types.MappingProxyType)):
        raise _refuse("wrong-type", f"{where} must be a duration object")
    basis = value.get("basis")
    if basis not in _ah().DURATION_BASES:
        raise _refuse("unknown-value",
                      f"{where} is measured on {basis!r}; the declared bases are "
                      f"{', '.join(_ah().DURATION_BASES)}")
    return {"basis": basis, "seconds": value.get("seconds"), "source": value.get("source")}


def attempt_facts(history, prediction_at):
    """The attempt projection -> one placed fact per record.

    A fact carries the attempt's own outcome and failure class. Both are legitimate FEATURES
    when the attempt finished before the decision was taken -- an earlier failure is exactly
    what a recovery decision is taken on -- and both are OUTCOME EVIDENCE when it finished
    after. `placement` is what decides which, and nothing else in this module may.
    """
    if not isinstance(history, (list, tuple)):
        raise _refuse("wrong-type", "the attempt history must be a list of records")
    if len(history) > MAX_HISTORY_RECORDS:
        raise _refuse("bounds-exceeded",
                      f"{len(history)} attempt records were supplied; the ceiling is "
                      f"{MAX_HISTORY_RECORDS}")
    facts = []
    for index, rec in enumerate(history):
        _history_record(rec, f"attempt history[{index}]")
        cls = rec.get("failure_class")
        facts.append({
            "observable": "attempt-outcome",
            "source": "attempt-outcome",
            # A NEW object over the record's scalars, never the record itself. This is the whole
            # of the read-only guarantee on this side: a row that handed back the projection's
            # own dict would let a reader annotating a row edit the evidence it read.
            "ref": {"kit": rec.get("kit"), "run": rec.get("run"), "task": rec.get("task"),
                    "attempt": rec.get("attempt"), "record_source": rec.get("source")},
            "ts": rec.get("ts"),
            "placement": placement(rec.get("ts"), prediction_at),
            "value": rec.get("result"),
            "abstained": False,
            "failure_class": cls,
            "failure_class_basis": "trusted-event" if cls else None,
            "deterministic_infrastructure": cls in DETERMINISTIC_FAILURE_CLASSES,
            "duration": _duration_entry(rec.get("duration"), f"attempt history[{index}].duration"),
            "observed_model": rec.get("observed_model"),
            "dispatched_model": rec.get("dispatched_model"),
        })
    return tuple(facts)


def _adjudication_value(verdict):
    if verdict == "solved":
        return "solved", False
    if verdict == "not-solved":
        return "not-solved", False
    return None, True


def trial_facts(trial, adjudications=(), run=None):
    """One evaluation trial -> the gradings it carries, each as its own observation.

    Read, never written. `workflow_eval.build_card` folds an adjudication INTO the trial record
    it was given; this function does not, because an evaluation that edits the record it is
    evaluating has changed the evidence. The trial dict handed in is untouched and everything
    lifted out of it is copied.

    A trial record carries no clock of its own, so every fact here is `unknown-time`. That is
    not a defect to paper over: grading happens after the run by construction, so these are
    outcome evidence and this module never places one among a row's features.
    """
    if trial is None:
        return ()
    if not isinstance(trial, (dict, types.MappingProxyType)):
        raise _refuse("wrong-type", "a trial is the record an evaluation envelope carries")
    ref = {"trial": trial.get("trial"), "task_id": trial.get("task_id"),
           "variant": trial.get("variant"), "run": run}
    facts = []

    def add(source, value, abstained=False, detail=None):
        facts.append({"observable": "trial-outcome", "source": source, "ref": _copy(ref),
                      "ts": None, "placement": "unknown-time", "value": value,
                      "abstained": abstained, "detail": detail})

    solved = trial.get("solved")
    if solved is True:
        add("tests-oracle", "solved")
    elif solved is False:
        add("tests-oracle", "not-solved")

    accepted = trial.get("accepted")
    by = trial.get("acceptance_by")
    if accepted is not None:
        source = "kit-acceptance" if by == "kit-check" else "review-verdict"
        add(source, "accepted" if accepted else "not-accepted", detail=by)
    review = trial.get("review") or {}
    if isinstance(review, (dict, types.MappingProxyType)) and review.get("verdict") == "unsure":
        add("review-verdict", None, abstained=True, detail="unsure")

    for entry in adjudications or ():
        if not isinstance(entry, (dict, types.MappingProxyType)):
            raise _refuse("wrong-type", "an adjudication is the object the envelope carries")
        if entry.get("trial") != trial.get("trial"):
            continue
        value, abstained = _adjudication_value(entry.get("verdict"))
        facts.append({"observable": "trial-outcome", "source": "human-adjudication",
                      "ref": {**_copy(ref), "by": entry.get("by")},
                      "ts": entry.get("at"), "placement": "unknown-time", "value": value,
                      "abstained": abstained, "detail": entry.get("verdict")})
    return tuple(facts)


def _trial_censoring(trial):
    reasons = []
    if trial is None:
        return reasons
    if trial.get("skipped"):
        reasons.append("trial-skipped")
    if trial.get("excluded"):
        reasons.append("trial-excluded")
    return reasons


# ---- labels ----------------------------------------------------------------------------------

def resolve_label(spec, declared, observations, censoring):
    """One question's label, with everything that produced it.

    Never picks. Two mapped values that differ make the label `disputed` and both provenances
    stay; that is the outcome the plan asks to be visible, and averaging it away is how an
    escaped defect becomes a rounding error.
    """
    block = {"question": f"{spec['id']}@{spec['version']}", "status": None, "value": None,
             "observations": [], "disagreement": [], "reasons": [], "sources": []}
    if declared is None:
        block["status"] = "censored" if censoring else "missing"
        block["reasons"].append("no-target-declared")
        return block
    mapping = declared["mapping"]
    mapped = []
    for fact in observations:
        if fact["observable"] != declared["observable"]:
            continue
        entry = {"source": fact["source"], "ref": _copy(fact["ref"]), "observed": fact["value"],
                 "observed_at": fact["ts"], "placement": fact["placement"],
                 "abstained": bool(fact["abstained"]), "label": None, "unmapped": False}
        if entry["abstained"] or fact["value"] is None:
            block["observations"].append(entry)
            continue
        label = mapping.get(fact["value"])
        if label is None:
            entry["unmapped"] = True
        else:
            entry["label"] = label
            mapped.append(entry)
        block["observations"].append(entry)
    block["sources"] = sorted({entry["source"] for entry in block["observations"]})
    values = sorted({entry["label"] for entry in mapped})
    if len(values) > 1:
        block["status"] = "disputed"
        block["disagreement"] = [{"source": entry["source"], "label": entry["label"],
                                  "observed": entry["observed"],
                                  "human": entry["source"] in HUMAN_LABEL_SOURCES}
                                 for entry in mapped]
        block["reasons"].append("sources-disagree")
    elif values:
        block["status"] = "resolved"
        block["value"] = values[0]
    elif censoring:
        block["status"] = "censored"
        block["reasons"].extend(censoring)
    else:
        block["status"] = "missing"
        if any(entry["unmapped"] for entry in block["observations"]):
            block["reasons"].append("observation-unmapped")
        elif any(entry["abstained"] for entry in block["observations"]):
            block["reasons"].append("observations-abstained")
        else:
            block["reasons"].append("no-observation")
    return block


# ---- actions -----------------------------------------------------------------------------------

def _alternatives(alternatives, taken, outcome):
    """Every eligible alternative, with an outcome on exactly the one that was taken.

    The conditional below is the whole of the "no untried-action claim" guarantee. There is no
    second path that fills this slot, and a refused decision takes no action at all, so every
    alternative on such a row is untried by construction.
    """
    rows = []
    for action in alternatives:
        is_taken = taken is not None and action == taken
        rows.append({
            "action": action,
            "taken": is_taken,
            "outcome": _copy(outcome) if is_taken else None,
            "outcome_basis": "observed-after-prediction" if is_taken else None,
            "why": None if is_taken else UNTRIED_ACTION_NOTE,
        })
    return rows


def _observed_outcome(after_facts):
    """The last attempt outcome recorded after the prediction instant, or None.

    "Last" is by timestamp among the facts the join placed after the decision. It is the outcome
    that FOLLOWED the decision and is never described as the outcome the decision produced --
    see `NO_CAUSAL_CLAIM`.
    """
    dated = [fact for fact in after_facts if _instant(fact["ts"]) is not None]
    if not dated:
        return None
    last = max(dated, key=lambda fact: _instant(fact["ts"]))
    return {"result": last["value"], "ref": _copy(last["ref"]), "ts": last["ts"],
            "failure_class": last["failure_class"],
            "failure_class_basis": last["failure_class_basis"],
            "deterministic_infrastructure": last["deterministic_infrastructure"],
            "note": INFRASTRUCTURE_FACT_NOTE if last["deterministic_infrastructure"] else None}


def _recovery(after_facts, intervention):
    """A failure followed by a pass, placed in order and claimed as nothing more."""
    dated = sorted((fact for fact in after_facts if _instant(fact["ts"]) is not None),
                   key=lambda fact: _instant(fact["ts"]))
    failure = next((fact for fact in dated if fact["value"] in FAILED_RESULTS), None)
    if failure is None:
        return None
    later = [fact for fact in dated
             if _instant(fact["ts"]) > _instant(failure["ts"])
             and fact["value"] in RECOVERED_RESULTS]
    if not later:
        return None
    return {
        "failure": {"ref": _copy(failure["ref"]), "ts": failure["ts"],
                    "result": failure["value"], "failure_class": failure["failure_class"],
                    "failure_class_basis": failure["failure_class_basis"],
                    "deterministic_infrastructure": failure["deterministic_infrastructure"]},
        "recovery": {"ref": _copy(later[0]["ref"]), "ts": later[0]["ts"],
                     "result": later[0]["value"]},
        "relation": "followed",
        "intervention": intervention,
        "causal_claim": None,
        "note": NO_CAUSAL_CLAIM,
    }


# ---- the refusal that has no record ------------------------------------------------------------

def _refusal(value):
    """A selection that refused, in the policy module's own reason vocabulary.

    A refused decision produces NO `DecisionRecord` at this contract revision -- the selection
    sets no action and the record requires one -- so there is nothing to join and nothing here
    invents a record shape to stand in for it. The row says the decision was refused, says why
    in the vocabulary of the module that refused, and is censored.
    """
    if not isinstance(value, (dict, types.MappingProxyType)):
        raise _refuse("wrong-type", "a refusal is an object naming the reasons it carried")
    extra = sorted(set(value) - {"reasons", "text"})
    if extra:
        raise _refuse("unknown-field",
                      f"a refusal carries {', '.join(repr(e) for e in extra)}")
    reasons = value.get("reasons")
    if not isinstance(reasons, (list, tuple)) or not reasons:
        raise _refuse("missing-field",
                      "a refusal names at least one reason; a refusal nobody can count is not "
                      "one")
    if len(reasons) > MAX_REFUSAL_REASONS:
        raise _refuse("bounds-exceeded", f"a refusal carries {len(reasons)} reasons")
    permitted = set(_dp().REFUSAL_REASONS)
    for reason in reasons:
        if reason not in permitted:
            raise _refuse("unknown-value",
                          f"{reason!r} is not one of the reasons a selection refuses for; the "
                          f"vocabulary is bin/decision_policy.py's own")
    text = value.get("text")
    if text is not None and not isinstance(text, str):
        raise _refuse("wrong-type", "a refusal's text is text")
    return {"reasons": list(reasons), "text": text}


# ---- the envelope ------------------------------------------------------------------------------

def _envelope(envelope, trial_id):
    """The evaluation envelope's own references, read and copied, never written back."""
    if envelope is None:
        if trial_id is not None:
            raise _refuse("missing-field",
                          "a trial was named but no evaluation envelope was supplied")
        return None, (), None
    if not isinstance(envelope, (dict, types.MappingProxyType)):
        raise _refuse("wrong-type", "the evaluation envelope must be an object")
    if envelope.get("v") != _we().EVAL_VERSION:
        raise _refuse("unknown-value",
                      f"the envelope is stamped {envelope.get('v')!r}; this join reads "
                      f"{_we().EVAL_VERSION!r}")
    holdout = envelope.get("holdout") or {}
    refs = {"run": envelope.get("run_id"), "repo": envelope.get("repo"),
            "harness": envelope.get("harness"),
            "partition": holdout.get("partition"),
            "manifest_ref": _copy(holdout.get("manifest_ref"))}
    if trial_id is None:
        return None, (), refs
    trial = next((rec for rec in envelope.get("trials") or ()
                  if isinstance(rec, (dict, types.MappingProxyType))
                  and rec.get("trial") == trial_id), None)
    if trial is None:
        raise _refuse("value-invalid",
                      f"the envelope carries no trial {trial_id!r}")
    return trial, tuple(envelope.get("adjudications") or ()), refs


# ---- the row -------------------------------------------------------------------------------------

def join_row(request, *, prediction_at, result=None, record=None, refusal=None, targets=(),
             history=(), envelope=None, trial_id=None, window_closes_at=None, as_of=None):
    """One decision, everything knowable when it was taken, and everything observed since.

    `prediction_at` is required and may be explicitly `None`. Nothing in a `DecisionRecord`
    carries the instant the decision was taken -- the record versions what was decided, not
    when -- so the caller supplies it, and a caller that cannot is telling the truth by passing
    `None`. A row with no prediction instant has no features at all and says so.
    """
    req = _payload_of(request, _contract().CONTRACT_VERSION, "the request")
    res = (None if result is None
           else _payload_of(result, _contract().CONTRACT_VERSION, "the result"))
    rec = (None if record is None
           else _payload_of(record, _contract().CONTRACT_VERSION, "the record"))
    if res is not None and res["correlation_id"] != req["correlation_id"]:
        raise _refuse("correlation-mismatch",
                      f"the result answers {res['correlation_id']!r} and the request is "
                      f"{req['correlation_id']!r}")
    if rec is not None and rec["correlation_id"] != req["correlation_id"]:
        raise _refuse("correlation-mismatch",
                      f"the record is about {rec['correlation_id']!r} and the request is "
                      f"{req['correlation_id']!r}")
    if rec is not None and refusal is not None:
        raise _refuse("value-invalid",
                      "a decision that refused has no record and a decision with a record did "
                      "not refuse; this row claims both")
    refused = None if refusal is None else _refusal(refusal)
    if prediction_at is not None and _instant(prediction_at) is None:
        raise _refuse("value-invalid",
                      f"the prediction instant {prediction_at!r} names no instant; pass an "
                      f"ISO-8601 timestamp with a zone, or None for 'nobody recorded it'")
    declared = _targets(targets, req)
    trial, adjudications, eval_refs = _envelope(envelope, trial_id)

    attempts = attempt_facts(history, prediction_at)
    features = [fact for fact in attempts if fact["placement"] == "at-or-before-prediction"]
    future = [fact for fact in attempts if fact["placement"] == "after-prediction"]
    undated = [fact for fact in attempts if fact["placement"] == "unknown-time"]
    graded = trial_facts(trial, adjudications, run=(eval_refs or {}).get("run"))

    censoring = []
    for fact in future:
        reason = CENSORING_BY_RESULT.get(fact["value"])
        if reason and reason not in censoring:
            censoring.append(reason)
    for reason in _trial_censoring(trial):
        if reason not in censoring:
            censoring.append(reason)
    if rec is None:
        censoring.append("refusal-has-no-record" if refused else "decision-record-absent")
    if window_closes_at is not None:
        closes, now = _instant(window_closes_at), _instant(as_of)
        if closes is None:
            raise _refuse("value-invalid",
                          f"the observation window closes at {window_closes_at!r}, which names "
                          f"no instant")
        if now is None or now < closes:
            censoring.append("observation-window-open")

    unresolved = []
    if rec is None:
        unresolved.append("refusal-has-no-record" if refused else "decision-record-absent")
    if prediction_at is None:
        unresolved.append("prediction-time-unknown")
    if not declared:
        unresolved.append("no-target-declared")

    observations = tuple(future) + tuple(undated) + tuple(graded)
    questions = []
    for spec in req["questions"]:
        qualified = f"{spec['id']}@{spec['version']}"
        answer = (res or {}).get("answers", {}).get(qualified)
        questions.append({
            "question": qualified,
            "kind": spec["kind"],
            "outcomes": list(spec["outcomes"]),
            "abstention": spec["abstention"],
            "target": _copy(declared.get(qualified)),
            "answer": _copy(answer),
            "label": resolve_label(spec, declared.get(qualified), observations, censoring),
        })

    outcome = _observed_outcome(future)
    taken = rec["selected"] if rec else None
    row = {
        "v": JOIN_VERSION,
        "correlation_id": req["correlation_id"],
        "run": req["run"],
        "task": req["task"],
        "attempt": req["attempt"],
        "intended_use": req["intended_use"],
        "prediction_at": prediction_at,
        "unresolved": unresolved,
        "censoring": censoring,
        "decision": {
            "record": None if rec is None else {
                "decision_id": rec["decision_id"], "mode": rec["mode"],
                "baseline": rec["baseline"], "recommended": rec["recommended"],
                "selected": rec["selected"], "bundle_sha": rec["bundle_sha"],
                "reason_codes": _copy(rec["reason_codes"]), "rejected": _copy(rec["rejected"]),
                "result_status": rec["result_status"],
                "admission_ref": _copy(rec["admission_ref"]),
                "attempt_ref": _copy(rec["attempt_ref"]),
                "duration": _duration_entry(rec["duration"], "the record's duration"),
            },
            "refusal": refused,
            "result_status": (res or {}).get("status"),
            "provider": {"requested": (res or {}).get("requested_provider"),
                         "dispatched": (res or {}).get("dispatched_provider"),
                         "observed": (res or {}).get("observed_provider")},
            "model": {"requested": (res or {}).get("requested_model"),
                      "dispatched": (res or {}).get("dispatched_model"),
                      "observed": (res or {}).get("observed_model")},
            "usage": _copy((res or {}).get("usage")),
            "note": None,
            "note_withheld": NOTE_WITHHELD,
        },
        # `outcome` is scoped to `taken`: it reports what followed the action this decision
        # took. With no action taken there is no such thing, and filling the slot from the
        # attempt log anyway would read as "the decision's outcome was pass" to anyone who did
        # not also check `taken`. The alternatives have always said so with a null and a note;
        # this slot now says it the same way, and `outcome_evidence` still carries the fact.
        "actions": {
            "baseline": rec["baseline"] if rec else None,
            "recommended": (res or {}).get("recommended"),
            "taken": taken,
            "outcome": None if taken is None else _copy(outcome),
            "why": None if taken is not None else NO_ACTION_OUTCOME_NOTE,
            "alternatives": _alternatives(req["alternatives"], taken, outcome),
        },
        "questions": questions,
        # The three buckets hold the fact objects `attempt_facts` built, which are new dicts over
        # the projection's scalars and alias nothing the caller owns. `outcome_evidence` re-lists
        # the same facts under their other role and is COPIED, so the two views of one fact can
        # never be the same object -- a reader annotating evidence would otherwise be editing a
        # feature. One copy, in the one place it is observable; a second here would mask it.
        "features": {
            "at_prediction": features,
            "excluded_as_future": future,
            "unknown_time": undated,
        },
        "outcome_evidence": _copy(list(future) + list(graded)),
        "recovery": _recovery(future, taken),
        "evaluation": eval_refs,
        "trial": None if trial is None else {"trial": trial.get("trial"),
                                             "task_id": trial.get("task_id"),
                                             "variant": trial.get("variant"),
                                             "skipped": trial.get("skipped"),
                                             "excluded": trial.get("excluded")},
        "disclosures": [UNTRIED_ACTION_NOTE, NO_CAUSAL_CLAIM, DURATIONS_SEPARATE, NOTE_WITHHELD],
    }
    return assert_no_causal_claim(row)


# ---- durations, kept apart -----------------------------------------------------------------------

def duration_by_basis(row):
    """Every duration in one row, grouped by the clock that measured it. Never summed.

    A decision's own latency is `decision-latency`; a dispatch's wall clock is `process-wall`.
    `attempt_history.DURATION_BASES` declares them separate facts, and a join that added them
    would report a number no clock ever measured.
    """
    grouped = {basis: [] for basis in _ah().DURATION_BASES}
    decision = ((row.get("decision") or {}).get("record") or {}).get("duration")
    if decision:
        grouped[decision["basis"]].append(_copy(decision))
    buckets = (row.get("features") or {})
    for key in ("at_prediction", "excluded_as_future", "unknown_time"):
        for fact in buckets.get(key) or ():
            entry = fact.get("duration")
            if entry:
                grouped[entry["basis"]].append(_copy(entry))
    return {"by_basis": grouped, "note": DURATIONS_SEPARATE}


# ---- the join ------------------------------------------------------------------------------------

def coverage(rows):
    """What the join could and could not resolve, counted rather than filtered."""
    counts = {"rows": len(rows), "questions": 0,
              "label_status": {status: 0 for status in LABEL_STATUSES},
              "censoring": {reason: 0 for reason in CENSORING_REASONS},
              "unresolved": {reason: 0 for reason in UNRESOLVED_REASONS},
              "facts": {placed: 0 for placed in FACT_PLACEMENTS},
              "label_sources": {source: 0 for source in LABEL_SOURCES},
              "rows_without_prediction_time": 0,
              "untried_alternatives": 0, "actions_taken": 0}
    for row in rows:
        if row.get("prediction_at") is None:
            counts["rows_without_prediction_time"] += 1
        for reason in row.get("censoring") or ():
            if reason in counts["censoring"]:
                counts["censoring"][reason] += 1
        for reason in row.get("unresolved") or ():
            if reason in counts["unresolved"]:
                counts["unresolved"][reason] += 1
        buckets = row.get("features") or {}
        counts["facts"]["at-or-before-prediction"] += len(buckets.get("at_prediction") or ())
        counts["facts"]["after-prediction"] += len(buckets.get("excluded_as_future") or ())
        counts["facts"]["unknown-time"] += len(buckets.get("unknown_time") or ())
        for question in row.get("questions") or ():
            counts["questions"] += 1
            label = question.get("label") or {}
            if label.get("status") in counts["label_status"]:
                counts["label_status"][label["status"]] += 1
            for source in label.get("sources") or ():
                if source in counts["label_sources"]:
                    counts["label_sources"][source] += 1
        for alternative in (row.get("actions") or {}).get("alternatives") or ():
            if alternative.get("taken"):
                counts["actions_taken"] += 1
            else:
                counts["untried_alternatives"] += 1
    return counts


def join(rows, notes=()):
    """Rows into one document, with its coverage and the claims it declines to make."""
    if not isinstance(rows, (list, tuple)):
        raise _refuse("wrong-type", "a join is built from a list of rows")
    if len(rows) > MAX_ROWS:
        raise _refuse("bounds-exceeded", f"{len(rows)} rows; the ceiling is {MAX_ROWS}")
    for index, row in enumerate(rows):
        if not isinstance(row, (dict, types.MappingProxyType)):
            raise _refuse("wrong-type", f"row[{index}] is not a joined row")
        if row.get("v") != JOIN_VERSION:
            raise _refuse("unknown-value",
                          f"row[{index}] is stamped {row.get('v')!r}; this join is "
                          f"{JOIN_VERSION!r}")
    return {
        "v": JOIN_VERSION,
        "rows": list(rows),
        "coverage": coverage(rows),
        "disclosures": [UNTRIED_ACTION_NOTE, NO_CAUSAL_CLAIM, DURATIONS_SEPARATE,
                        INFRASTRUCTURE_FACT_NOTE, NOTE_WITHHELD],
        "notes": list(notes),
    }


# ---- D15: calibration reporting ----------------------------------------------------------------
#
# WHAT WAS WRONG. A `DecisionResult` carries two numeric slots for a question -- `raw` and
# `calibrated` -- and D14's join already carries both, alongside the label the join resolved, in
# every question block of every row. Nothing counted how often either one agreed with what
# happened. Without that, "the model is well-calibrated" is a claim nobody has checked, and a
# rules provider's plain categorical choice (`raw` and `calibrated` both `None`, by
# `bin/decision_provider.py`'s own construction) is exactly the kind of value a careless report
# turns into a fake probability -- scored as though it had said "0% confident" rather than "no
# confidence was ever claimed".
#
# WHAT THIS IS. Two things, kept apart on purpose:
#
#   * `calibration_artifact` records IDENTITY -- which target, provider, model, domain, dataset,
#     method, partition and how many rows a calibrator claims to have been fit on -- and nothing
#     else. No observation, no prediction, no label crosses this function; there is nothing here
#     a fit could be computed FROM, because fitting one is `OPTIONAL-TASKS.md`'s O03, not
#     started, and this module's job is to let a report cite an artifact without ever producing
#     one.
#   * `calibration_report` (and `calibration_report_pair`, which runs it once per field) counts,
#     for ONE question and ONE of `raw`/`calibrated`, how the join's own `answer.outcome`,
#     `answer.raw` and `answer.calibrated` compared against the label the join resolved:
#     classification accuracy for every scoreable row, Brier score and log loss for the rows
#     that actually carry a distribution in that field, a reliability diagram over the
#     distribution's top category, and false-action risk at candidate thresholds the CALLER
#     names -- there is no default threshold, because inventing one would be deciding what
#     "acting" means on the caller's behalf.
#
# WHAT IT REFUSES. A report on `field="raw"` cannot cite a calibration artifact -- a raw score
# was never fit on anything, and citing one beside it would dress an unfit number up as
# validated. A report on `field="calibrated"` that DOES cite one must match the artifact's own
# pinned question and must declare which partition its own rows come from; a report whose
# partition equals the artifact's `fit_partition` is refused outright, because scoring a
# calibrator on the very material it was fit on is the fit read back, not held-out evidence --
# the same distinction `bin/workflow_eval.PARTITION_ROLES` draws between a partition that may be
# fit on and one that is held out, expressed here as a caller-declared label this module checks
# for equality rather than a second copy of that vocabulary (D14's own sibling-reach test pins
# exactly four names on exactly four modules; a fifth reach here would break it). A label that is
# `disputed`, `missing` or `censored` is EXCLUDED from every metric's numerator and denominator,
# never guessed at, and its exclusion is counted, not silently dropped. A sample too small to
# report with a straight face says `insufficient-evidence` rather than a number; a field with no
# distribution at all -- a rules provider's answer, or an answer this report was not asked to
# score -- says `not-applicable`, because "no probability was ever claimed" and "the probability
# claimed was 0" are different facts and this module refuses to collapse them into one. That
# floor is EVERY metric's, the reliability diagram's own bins included: each bin carries its own
# status, and an occupied bin below the floor reports `insufficient-evidence` with its `n` and
# its `mean_confidence` visible rather than an `empirical_accuracy` that one observation makes
# 1.0 or 0.0. An artifact's VALUES are checked wherever one enters -- built here or imported as
# a payload -- by the single `_assert_artifact_values`, so a garbage-provenance object with the
# right field set and the right version stamp is refused by the report, not echoed into it.
#
# WHAT IT NEVER DOES. Reporting on `calibrated` never reads `raw` when `calibrated` is absent,
# and reporting on `raw` never reads `calibrated`: each call scores exactly the field it was
# asked to score, and the two are always returned in separate keys, never combined into one
# number. `vendor_confidence` is never read by anything in this section -- it is, by the
# decision contract's own design, not a probability of task success, and no metric here treats
# it as one. And nothing here fits: there is no function anywhere in this module that takes a
# batch of predictions and labels and returns calibration PARAMETERS: this is a reader of numbers
# some other owner already produced, exactly as the rest of this module reads projections some
# other owner already wrote.

#: This report's own schema, pinned separately from `JOIN_VERSION` for the reason `JOIN_VERSION`
#: is pinned separately from the decision contract's: a calibration artifact and a calibration
#: report are a THIRD and FOURTH object, neither a decision nor a join row. Registered in
#: `release_gate.VERSION_SOURCES` in its own right.
CALIBRATION_VERSION = "polytropos.decision-calibration/1"

#: What a computed metric's own status can be. `not-applicable` is a valid question with nothing
#: to score in this field at all (a rules provider's answer, every time, on that field);
#: `insufficient-evidence` is a field that DOES carry probabilities, just too few of them to
#: report as a number rather than noise.
METRIC_STATUSES = ("computed", "not-applicable", "insufficient-evidence")

#: Below this many scoreable rows a metric reports `insufficient-evidence` rather than a number.
#: Not derived from a formula -- a documented floor beneath which a rate or a mean computed from
#: this few observations reads as more confident than it is. A caller running a synthetic
#: fixture may override it; production reporting should not, and nothing here has a seam to
#: quietly change the shipped floor from outside a test.
MIN_METRIC_SAMPLES = 20

#: The reliability diagram's own bin count, absent a caller override. This is a REPORTING
#: granularity -- how the same already-observed evidence is grouped for reading -- never a
#: fitted parameter, so a default here carries none of the risk a default calibration METHOD
#: would.
DEFAULT_RELIABILITY_BINS = 10

#: A floor under a probability log loss takes the logarithm of. A provider that claimed
#: probability exactly 0 for the outcome that then happened is not rewarded with an
#: uninformative infinity, nor is its claim quietly rounded away: the floor is applied and EVERY
#: application of it is counted in the metric's own `clipped` field, so a reader can see how
#: often it happened rather than trusting a finite number that hides it.
LOG_LOSS_FLOOR = 1e-9

#: A calibration artifact's exact field set. Closed, the same way `_refusal`'s field set is
#: closed: an artifact is an audit object, and an unrecognised extra key beside its pins is a
#: caller's mistake this module refuses rather than silently carrying forward.
CALIBRATION_ARTIFACT_KEYS = ("v", "target", "provider", "model", "domain", "dataset", "method",
                             "fit_partition", "sample_count", "fitted_at", "note")

RULE_LABEL_NOTE = (
    "an outcome with no raw or calibrated distribution is a rule's label, not a probability of "
    "zero: it is excluded from every metric that scores a distribution, counted under "
    "no-distribution, and never converted into one by assuming a value"
)

RAW_VS_CALIBRATED_NOTE = (
    "this report scores exactly one of raw or calibrated per call and never both at once, so a "
    "raw score and a calibrated score are never blended into one number; calibration_report_pair "
    "returns the two separately for the same reason"
)


_LN2 = 0.6931471805599453


def _ln(x):
    """Natural log, computed without importing anything: this module's imports are pinned to
    `datetime, importlib.util, pathlib, re, types` by its own read-only-by-construction test, so
    log loss's `-log(p)` is built here from arithmetic alone -- range-reduce `x` to within
    [0.75, 1.5) by repeated halving/doubling (tracked as a power of two, `_LN2` away from zero),
    then sum the Mercator series for the reduced value. Verified in tests against known values
    (`ln(2)`, `ln(0.5)`, `ln(10)`) rather than trusted on the strength of the derivation alone.
    """
    if not isinstance(x, (int, float)) or isinstance(x, bool) or x <= 0:
        raise _refuse("value-invalid", f"ln() needs a positive number, got {x!r}")
    value = float(x)
    power = 0
    while value > 1.5:
        value /= 2.0
        power += 1
    while value < 0.75:
        value *= 2.0
        power -= 1
    y = value - 1.0
    total = 0.0
    term = y
    n = 1
    while abs(term) > 1e-15 and n < 200:
        total += term / n
        term *= -y
        n += 1
    return total + power * _LN2


def _assert_artifact_values(pinned):
    """The ONE place a calibration artifact's VALUES are judged: blank identity text, a negative
    or non-integer sample count, a `fitted_at` that names no instant, a note that is not text.

    Both ways an artifact can reach a report end here -- `calibration_artifact`, which builds one
    in this process, and `_validated_artifact`, which reads one some other owner produced. That
    was not true before: the value checks lived in the constructor alone, so a payload carrying
    the right FIELD SET and the right version stamp (blank provider, `sample_count` -999, a
    `fitted_at` that is prose) was echoed into an audited report as a validated pin while the
    constructor refused the identical values -- and the consumption path is the one every real
    caller uses. One implementation, called twice; a second copy beside it would be the defect
    this is the fix for, not another fix.
    """
    for field in ("target", "provider", "domain", "dataset", "method", "fit_partition"):
        value = pinned.get(field)
        if not isinstance(value, str) or not value.strip():
            raise _refuse(
                "wrong-type",
                f"a calibration artifact's {field} is non-empty text naming what was fit; an "
                f"artifact records an identity, never the observations behind one")
    model = pinned.get("model")
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise _refuse("wrong-type", "a calibration artifact's model is non-empty text, or null")
    sample_count = pinned.get("sample_count")
    if not isinstance(sample_count, int) or isinstance(sample_count, bool) or sample_count < 0:
        raise _refuse(
            "wrong-type",
            "a calibration artifact's sample_count is a non-negative integer -- the count a fit "
            "elsewhere claims to have used, never the observations themselves; nothing with "
            "that shape is a parameter of the constructor")
    fitted_at = pinned.get("fitted_at")
    if fitted_at is not None and _instant(fitted_at) is None:
        raise _refuse("value-invalid",
                      f"fitted_at {fitted_at!r} names no instant; pass an ISO-8601 timestamp "
                      f"with a zone, or None for 'unknown'")
    if not isinstance(pinned.get("note"), str):
        raise _refuse("wrong-type", "a calibration artifact's note is text")
    return pinned


def calibration_artifact(*, target, provider, domain, dataset, method, fit_partition,
                         sample_count, model=None, fitted_at=None, note=""):
    """A pin, never a fit: what a calibrator CLAIMS to be, recorded so a report can refuse to
    trust a `calibrated` distribution whose artifact does not match the question it is asked
    about, or was fit on the very partition it is now being validated against.

    Every keyword here is IDENTITY -- a label, a count, an instant -- never a collection of
    predictions or labels. There is no parameter this function could receive that a fit could be
    computed from, which is the whole of why this function cannot become one.

    The values themselves are judged by `_assert_artifact_values`, which `_validated_artifact`
    calls too, so building an artifact here and importing one with the same shape cannot diverge.
    """
    return _assert_artifact_values(
        {"v": CALIBRATION_VERSION, "target": target, "provider": provider, "model": model,
         "domain": domain, "dataset": dataset, "method": method,
         "fit_partition": fit_partition, "sample_count": sample_count,
         "fitted_at": fitted_at, "note": note})


def _validated_artifact(value):
    """A calibration artifact, checked against its own closed field set, its version AND its
    values -- whether it was built by `calibration_artifact` in this process or IMPORTED as a
    payload some other owner (a future O03, or a synthetic test fixture) produced with this same
    shape. The shape checks run first and the value checks last, so a refusal names which of the
    two actually fired rather than leaving a caller to guess."""
    if not isinstance(value, (dict, types.MappingProxyType)):
        raise _refuse("wrong-type",
                      "a calibration artifact is the object calibration_artifact() returns")
    extra = sorted(set(value) - set(CALIBRATION_ARTIFACT_KEYS))
    if extra:
        raise _refuse("unknown-field",
                      f"a calibration artifact carries {', '.join(repr(e) for e in extra)}, "
                      f"which is not one of its declared fields")
    missing = sorted(set(CALIBRATION_ARTIFACT_KEYS) - set(value))
    if missing:
        raise _refuse("missing-field",
                      f"a calibration artifact is missing {', '.join(repr(m) for m in missing)}")
    if value.get("v") != CALIBRATION_VERSION:
        raise _refuse("unknown-value",
                      f"the artifact is stamped {value.get('v')!r}; this report reads "
                      f"{CALIBRATION_VERSION!r}")
    return _assert_artifact_values(dict(value))


def _standard_error(rate, n):
    """The standard error of a proportion under a normal approximation -- the one uncertainty
    measure this module reports beside a rate. `n < 2` returns `None`: a spread computed from
    fewer than two observations is not an uncertainty measure, it is noise dressed as one."""
    if n < 2:
        return None
    return ((rate * (1.0 - rate)) / n) ** 0.5


def _mean_and_standard_error(values):
    """A sample mean and its standard error, or `(None, None)` for an empty sample."""
    n = len(values)
    if n == 0:
        return None, None
    mean = sum(values) / n
    if n < 2:
        return mean, None
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, (variance / n) ** 0.5


def _rate_metric(successes, n, min_n):
    """A success rate, or the honest reason there is none to report yet."""
    if n < min_n:
        return {"status": "insufficient-evidence", "value": None, "n": n,
                "successes": successes, "standard_error": None}
    rate = successes / n
    return {"status": "computed", "value": rate, "n": n, "successes": successes,
            "standard_error": _standard_error(rate, n)}


def _brier_metric(prob_rows, min_n):
    """The multi-category Brier score (Brier, 1950): the mean, over scoreable rows, of the sum
    over every one of the question's OWN outcomes of `(predicted - actual)^2`, where `actual` is
    1 for the outcome the label resolved to and 0 for every other. This generalises across
    boolean, choice and ordinal questions without singling out an arbitrary "positive" category."""
    if not prob_rows:
        return {"status": "not-applicable", "value": None, "n": 0, "standard_error": None}
    values = [sum((dist.get(o, 0.0) - (1.0 if o == actual else 0.0)) ** 2 for o in outcomes)
              for dist, actual, outcomes in prob_rows]
    if len(values) < min_n:
        return {"status": "insufficient-evidence", "value": None, "n": len(values),
                "standard_error": None}
    mean, se = _mean_and_standard_error(values)
    return {"status": "computed", "value": mean, "n": len(values), "standard_error": se}


def _log_loss_metric(prob_rows, min_n):
    """Mean log loss: `-ln(predicted probability of the outcome that actually happened)`,
    floored at `LOG_LOSS_FLOOR` with every floored observation counted in `clipped`."""
    if not prob_rows:
        return {"status": "not-applicable", "value": None, "n": 0, "standard_error": None,
                "clipped": 0}
    losses, clipped = [], 0
    for dist, actual, _outcomes in prob_rows:
        probability = dist.get(actual, 0.0)
        if probability < LOG_LOSS_FLOOR:
            probability = LOG_LOSS_FLOOR
            clipped += 1
        losses.append(-_ln(probability))
    if len(losses) < min_n:
        return {"status": "insufficient-evidence", "value": None, "n": len(losses),
                "standard_error": None, "clipped": clipped}
    mean, se = _mean_and_standard_error(losses)
    return {"status": "computed", "value": mean, "n": len(losses), "standard_error": se,
            "clipped": clipped}


def _reliability_bins(prob_rows, bins, min_n):
    """A confidence-calibration reliability diagram: each scoreable row contributes its TOP
    predicted category and whether that category matched the label, binned by how confident the
    prediction was. Empty bins are reported with `n: 0` rather than omitted, the same discipline
    D14 applies to a censored row -- an empty bin is evidence about the distribution of
    confidence, not an absence to hide.

    Every bin carries its own `METRIC_STATUSES` status against the SAME floor the four metrics
    beside it already take, because a bin's `empirical_accuracy` is a rate estimated from
    whatever landed in that bin, and a rate from one observation is 1.0 or 0.0 no matter what the
    model believed. Without the floor this function reported that 1.0 in the same call in which
    `classification` and `brier` were reporting `insufficient-evidence` over the very same row.

    The three cases stay distinguishable rather than collapsing into each other:

      * an EMPTY bin is `not-applicable` at `n: 0` -- nothing landed here to score, the same
        reading `_brier_metric` gives a field carrying no distributions at all;
      * an OCCUPIED bin below the floor is `insufficient-evidence` with its `n` and its
        `mean_confidence` still visible -- the confidences are what the predictions THEMSELVES
        said, not something estimated from outcomes -- and its `empirical_accuracy` and
        `standard_error` null, the same shape `_rate_metric` uses when it keeps `successes` but
        withholds `value`;
      * at or above the floor the rate is reported.

    `min_samples` stays the public, tested override it already was: a caller who knowingly passes
    1 gets a rate from one observation, visibly, the way the other four metrics honour it."""
    edges = [i / bins for i in range(bins + 1)]
    grouped = [[] for _ in range(bins)]
    for dist, actual, outcomes in prob_rows:
        top = max(outcomes, key=lambda o: dist.get(o, 0.0))
        confidence = dist.get(top, 0.0)
        index = min(int(confidence * bins), bins - 1)
        grouped[index].append((confidence, 1.0 if top == actual else 0.0))
    out = []
    for index in range(bins):
        entries = grouped[index]
        n = len(entries)
        if n == 0:
            out.append({"lower": edges[index], "upper": edges[index + 1],
                        "status": "not-applicable", "n": 0, "mean_confidence": None,
                        "empirical_accuracy": None, "standard_error": None})
            continue
        mean_confidence = sum(c for c, _ in entries) / n
        if n < min_n:
            out.append({"lower": edges[index], "upper": edges[index + 1],
                        "status": "insufficient-evidence", "n": n,
                        "mean_confidence": mean_confidence, "empirical_accuracy": None,
                        "standard_error": None})
            continue
        accuracy = sum(a for _, a in entries) / n
        out.append({"lower": edges[index], "upper": edges[index + 1], "status": "computed",
                    "n": n, "mean_confidence": mean_confidence,
                    "empirical_accuracy": accuracy,
                    "standard_error": _standard_error(accuracy, n)})
    return out


def _false_action_risk(prob_rows, action_outcome, thresholds, min_n):
    """For each candidate threshold: among the rows whose predicted probability of
    `action_outcome` is at or above it, the fraction whose label resolved to something else --
    the risk of acting on this signal at this threshold, with its own sample count and
    uncertainty, never a single number blended across thresholds."""
    out = []
    for threshold in sorted(set(thresholds)):
        eligible = [actual for dist, actual, _outcomes in prob_rows
                   if dist.get(action_outcome, 0.0) >= threshold]
        n = len(eligible)
        if n < min_n:
            out.append({"threshold": threshold, "status": "insufficient-evidence", "n": n,
                        "false_action_rate": None, "standard_error": None})
            continue
        wrong = sum(1 for actual in eligible if actual != action_outcome)
        rate = wrong / n
        out.append({"threshold": threshold, "status": "computed", "n": n,
                    "false_action_rate": rate, "standard_error": _standard_error(rate, n)})
    return out


def calibration_report(rows, *, question, field, artifact=None, report_partition=None,
                       thresholds=(), action_outcome=None, bins=DEFAULT_RELIABILITY_BINS,
                       min_samples=MIN_METRIC_SAMPLES):
    """One question, one interpretation of its numbers (`raw` or `calibrated`), and everything
    knowable about how well those numbers matched what the join resolved.

    `rows` are D14's own joined rows (or a synthetic fixture carrying the same shape, tagged with
    `JOIN_VERSION`) -- this function reads `questions[].answer` and `questions[].label` from
    each and computes nothing that was not already sitting in them.
    """
    if not isinstance(rows, (list, tuple)):
        raise _refuse("wrong-type", "calibration_report reads a list of joined rows")
    if len(rows) > MAX_ROWS:
        raise _refuse("bounds-exceeded", f"{len(rows)} rows; the ceiling is {MAX_ROWS}")
    if not isinstance(question, str) or not question.strip():
        raise _refuse("wrong-type", "calibration_report needs the qualified question id")
    if field not in ("raw", "calibrated"):
        raise _refuse("unknown-value", f"field must be 'raw' or 'calibrated', not {field!r}")
    if not isinstance(bins, int) or isinstance(bins, bool) or bins < 1:
        raise _refuse("wrong-type", "bins is a positive integer")
    if not isinstance(min_samples, int) or isinstance(min_samples, bool) or min_samples < 1:
        raise _refuse("wrong-type", "min_samples is a positive integer")

    pinned = None
    if artifact is not None:
        pinned = _validated_artifact(artifact)
        if field != "calibrated":
            raise _refuse(
                "value-invalid",
                "a calibration artifact pins what fit the CALIBRATED distribution; reporting on "
                "'raw' needs no artifact and cites none")
        if pinned["target"] != question:
            raise _refuse(
                "value-invalid",
                f"the artifact is pinned to {pinned['target']!r}, not {question!r}; a report "
                f"cannot cite an artifact fit for a different question")
        if report_partition is None:
            raise _refuse(
                "missing-field",
                "a report scored against a calibration artifact must declare which partition "
                "its own rows come from, so the fit partition can never be validated against "
                "itself by omission")
        if report_partition == pinned["fit_partition"]:
            raise _refuse(
                "value-invalid",
                f"this report's rows are declared as partition {report_partition!r}, the same "
                f"partition the artifact says it was fit on; that is the fit read back, not "
                f"held-out evidence")

    matched, unmatched = [], 0
    for index, row in enumerate(rows):
        if not isinstance(row, (dict, types.MappingProxyType)) or row.get("v") != JOIN_VERSION:
            raise _refuse(
                "wrong-type",
                f"row[{index}] is not a joined row this module's own join_row produced")
        item = next((q for q in row.get("questions") or () if q.get("question") == question),
                   None)
        if item is None:
            unmatched += 1
            continue
        matched.append(item)

    resolved = [q for q in matched if (q.get("label") or {}).get("status") == "resolved"]
    scoreable = [q for q in resolved
                if q.get("answer") is not None and not q["answer"].get("abstained")]
    abstained = len(resolved) - len(scoreable)

    correct = sum(1 for q in scoreable if q["answer"]["outcome"] == q["label"]["value"])
    classification = _rate_metric(correct, len(scoreable), min_samples)

    prob_rows = []
    no_distribution = 0
    for q in scoreable:
        dist = q["answer"].get(field)
        if dist is None:
            no_distribution += 1
            continue
        prob_rows.append((_copy(dist), q["label"]["value"], tuple(q["outcomes"])))

    brier = _brier_metric(prob_rows, min_samples)
    log_loss = _log_loss_metric(prob_rows, min_samples)
    reliability = _reliability_bins(prob_rows, bins, min_samples)

    action_risk = None
    if thresholds:
        if action_outcome is None:
            raise _refuse(
                "missing-field",
                "candidate thresholds need a declared action_outcome; this module does not "
                "guess which outcome a threshold is measuring risk against")
        for threshold in thresholds:
            if (not isinstance(threshold, (int, float)) or isinstance(threshold, bool)
                    or not (0.0 <= threshold <= 1.0)):
                raise _refuse("value-invalid",
                              f"a candidate threshold must be in [0, 1], got {threshold!r}")
        action_risk = _false_action_risk(prob_rows, action_outcome, thresholds, min_samples)

    report = {
        "v": CALIBRATION_VERSION,
        "question": question,
        "field": field,
        "artifact": _copy(pinned),
        "report_partition": report_partition,
        "coverage": {
            "rows": len(rows), "matched_rows": len(matched), "unmatched_rows": unmatched,
            "resolved": len(resolved), "scoreable": len(scoreable), "abstained": abstained,
            "excluded": {"label-not-resolved": len(matched) - len(resolved),
                        "no-distribution": no_distribution},
        },
        "classification": classification,
        "brier": brier,
        "log_loss": log_loss,
        "reliability_bins": reliability,
        "false_action_risk": action_risk,
        "notes": [RULE_LABEL_NOTE, RAW_VS_CALIBRATED_NOTE],
    }
    return assert_no_causal_claim(report)


def calibration_report_pair(rows, *, question, artifact=None, report_partition=None,
                            thresholds=(), action_outcome=None, bins=DEFAULT_RELIABILITY_BINS,
                            min_samples=MIN_METRIC_SAMPLES):
    """`raw` and `calibrated`, reported separately and never combined into one number.

    The artifact -- if there is one -- pins only the calibrated side. `raw` is always reported
    with no artifact, regardless of what was passed here: a raw score was never fit on anything,
    and citing an artifact beside it would misrepresent an unfit number as validated.
    """
    raw = calibration_report(rows, question=question, field="raw", artifact=None,
                             thresholds=thresholds, action_outcome=action_outcome, bins=bins,
                             min_samples=min_samples)
    calibrated = calibration_report(rows, question=question, field="calibrated",
                                    artifact=artifact, report_partition=report_partition,
                                    thresholds=thresholds, action_outcome=action_outcome,
                                    bins=bins, min_samples=min_samples)
    return {"raw": raw, "calibrated": calibrated}


# ---- D19: outcomes and stopping ------------------------------------------------------------------
#
# WHAT WAS WRONG. D18 built the EXPERIMENT SPECIFICATION -- three arms, a frozen held-out cohort,
# and the accounting a future run's results would be read through (`workflow_eval.arm_accounting`,
# `workflow_eval.compare_conditional_recovery`) -- and D15 built one question's calibration
# report. Nothing above this line assembled the two into the single document an operator would
# actually read before deciding whether to promote a candidate: quality beside regression,
# resources beside time, coverage beside censoring, a slice broken out from the whole, and --
# before any of the rest is read as more than a rehearsal -- whether the operator has PINNED every
# stop field this decision needs. A report that showed recovery numbers without that gate would
# let a complete-looking document stand in for a complete plan.
#
# WHAT THIS IS. `operator_plan` is the gate: six fields -- an independent label source, an
# observation window, a practical gain, a tolerated regression, an interim-look policy and a
# stopping rule -- predeclared before any live evaluation, with no default for any of them.
# `recovery_report` is the document: it reads a D14 join's own `coverage()` for row, label and
# censoring counts, an optional D15 `calibration_report_pair` for quality, an optional
# `quality_regression` for the paired change against the operator's own cap, `resource_evidence`
# over one or more `workflow_eval.arm_accounting` results for cost by scope, `time_by_basis` over
# the same join's rows for wall/latency by clock, `slice_coverage` for a caller-declared subgroup
# breakdown, `candidate_tally` for every candidate this evaluation tried or rejected and its
# exposure, and an optional `full_task_study` block and `comparisons` list carried straight
# through from D18's own protocol and accounting -- never recomputed here. Every report is
# labelled `synthetic` when the data behind it is, because nothing above this line has ever run a
# live evaluation.
#
# WHAT IT REFUSES. A missing operator field is `own-declarations-incomplete` and
# `blocks_promotion_on_these_fields` -- never a default this module invents, and never
# `insufficient-evidence`, which is a DATA problem `METRIC_STATUSES` already names and which an
# unset threshold is not. `resource_evidence` refuses a cost-per-accepted figure that is not
# `None` when nothing was accepted, and refuses a totals block that lost a basis or smuggled a
# priced `usd` figure under `proxy` or `unpriced` -- not a second computation of
# `workflow_eval.arm_accounting`'s own ratio, a refusal to relay evidence that no longer agrees
# with it. `quality_regression` reports no verdict without an operator-declared
# `allowed_quality_regression`, and invents no universal cap. Four of
# `RECOVERY_REPORT_DECLARATIONS`'s six names are spelled identically to four of
# `bin/workflow_eval.OPERATOR_DECLARATIONS`'s seven on purpose -- the same practical gain, the
# same tolerated regression, the same interim-look and stopping rules, declared at two different
# scopes -- and `tests/test_decision_trial_protocol.py` pins the two spellings equal rather than
# this module reaching across the module boundary for a second function call. `operator_plan`
# ALSO refuses to let that six-field completeness read as the whole of a live-run precondition
# set: `RECOVERY_PLAN_UNCOVERED_DECLARATIONS` names the three `workflow_eval.OPERATOR_DECLARATIONS`
# fields it does not cover, `not_covered` carries them with `workflow_eval.live_requirements`
# named as their owner, and `scope_note` travels into every `recovery_report`'s own `labels` --
# not only when this plan is incomplete -- so `own-declarations-complete` is never read alone as
# "nothing blocks promotion" (Phase 2 F4, its third appearance in this kit).
#
# WHAT IT NEVER DOES. `recovery_report` computes no cost, no duration, no calibration metric and
# no conditional-recovery rate itself: every number it carries was computed by an existing owner
# -- `workflow_eval.arm_accounting`, `workflow_eval.compare_conditional_recovery`, this module's
# own `coverage`, `duration_by_basis` and `calibration_report_pair` -- and this section only
# assembles, validates and labels what those owners already produced.

RECOVERY_REPORT_VERSION = "polytropos.decision-recovery-report/1"

#: This report's own predeclared operator inputs. `practical_gain_threshold`,
#: `allowed_quality_regression`, `interim_look_rule` and `stopping_rule` are spelled identically
#: to four of `bin/workflow_eval.OPERATOR_DECLARATIONS`'s seven names ON PURPOSE -- the pairing is
#: pinned by name in `tests/test_decision_trial_protocol.py`, not by this module reaching into
#: workflow_eval for a function call: decision_eval.py reads a sibling for VOCABULARY only (see
#: `_we`'s own docstring), and workflow_eval's OPERATOR_DECLARATIONS is D18's per-ARM
#: predeclaration, not this report's per-EVALUATION one -- two independent things kept spelled
#: alike rather than one reaching into the other. `independent_label_source` and
#: `observation_window` belong to the join layer alone and have no counterpart there.
RECOVERY_REPORT_DECLARATIONS = ("independent_label_source", "observation_window",
                                "practical_gain_threshold", "allowed_quality_regression",
                                "interim_look_rule", "stopping_rule")

#: The five cost bases `workflow_eval.add_cost`/`priced_usd` keep separate, mirrored here the same
#: way `RECOVERED_RESULTS`/`FAILED_RESULTS` above mirror a subset of another owner's vocabulary: a
#: literal this module reads FROM evidence, never a name it reaches across the module boundary to
#: fetch.
RESOURCE_BASES = ("model-reported", "estimated", "proxy", "credits", "unpriced")

#: The exact field set `resource_evidence` requires on every `workflow_eval.arm_accounting`
#: result before it will relay it. A result missing one of these is refused rather than padded.
ACCOUNTING_EVIDENCE_KEYS = ("arm", "collapsed_from", "items", "accepted", "failed", "censored",
                            "conditional_recovery", "initial_attempt", "scopes", "labels")

#: The exact field set inside each of an accounting's own `scopes[...]` blocks.
ACCOUNTING_SCOPE_KEYS = ("totals", "priced_usd", "scope", "items", "cost_per_accepted_usd",
                         "undefined_reason", "label")

#: What data a recovery report was built over. `synthetic` carries `SYNTHETIC_LABEL`; there is no
#: third value, because a report is either evidence from a real evaluation or it is not.
DATA_PROVENANCES = ("synthetic", "live")

#: The only two states `quality_regression` may return alongside a verdict. Never invented for
#: any other purpose.
REGRESSION_STATUSES = ("within-allowed-regression", "regression-exceeds-allowance")

#: Every outcome a candidate this evaluation considered can carry. A candidate that was tried and
#: then rejected stays counted -- it is not the same fact as one never tried.
CANDIDATE_STATUSES = ("tried", "accepted", "rejected")

#: The `workflow_eval.OPERATOR_DECLARATIONS` names this report's own plan does NOT cover.
#: `RECOVERY_REPORT_DECLARATIONS` shares four of D18's seven names by design (see its own
#: docstring); these are the other three -- `primary_endpoint` and `sample_size`, both required
#: by `workflow_eval.live_requirements` before a live trial, plus `independent_evaluation` -- and
#: `operator_plan` neither declares nor checks them. Phase 2's F4 shape (two halves each
#: enforcing part of a precondition, nothing composing them, each phrased as though it were the
#: whole) has appeared three times in this kit; this is the naming-level fix D18 used for the
#: first two, applied here: a hardcoded literal, never a reach into workflow_eval for a computed
#: difference (decision_eval.py calls no sibling function), pinned in BOTH directions by
#: `tests/test_decision_trial_protocol.py` against workflow_eval.OPERATOR_DECLARATIONS's whole
#: seven -- the four shared and these three uncovered must always partition it exactly.
RECOVERY_PLAN_UNCOVERED_DECLARATIONS = ("primary_endpoint", "sample_size",
                                       "independent_evaluation")

SCOPE_NOTE = (
    "this plan covers exactly RECOVERY_REPORT_DECLARATIONS's six fields and NO other stop "
    "field: workflow_eval.OPERATOR_DECLARATIONS's own primary_endpoint, sample_size and "
    "independent_evaluation (see RECOVERY_PLAN_UNCOVERED_DECLARATIONS) are "
    "workflow_eval.live_requirements's responsibility, not this module's, and are neither "
    "declared nor checked here. own_declarations_complete and "
    "blocks_promotion_on_these_fields describe ONLY this plan's own six fields -- reading "
    "either as a claim that nothing else blocks a live evaluation is exactly the misreading "
    "this note exists to rule out"
)

SYNTHETIC_LABEL = (
    "every figure in this report was computed over SYNTHETIC fixture data: no attempt behind it "
    "was dispatched, no checkpoint was restored and no acceptance check ran for real. A report "
    "built from a fixture carries this label so it is never read as evidence of a live outcome"
)

PLAN_INCOMPLETE_NOTE = (
    "a missing operator declaration means this plan is INCOMPLETE, not a value this module "
    "supplies by default: promotion is blocked until the operator pins every stop field. A thin "
    "plan is a different fact from a metric with insufficient evidence, and this module never "
    "reports one as the other"
)

NO_REGRESSION_CAP_NOTE = (
    "no operator-declared allowed_quality_regression was supplied; this module invents no "
    "universal cap and reports no verdict without one"
)

RESOURCE_EVIDENCE_NOTE = (
    "every figure here was computed by workflow_eval.arm_accounting and is relayed field for "
    "field; this module computes no cost of its own and refuses evidence that no longer agrees "
    "with that function's own zero-accepted and separate-bases invariants"
)


def _rr_mapping(value, where):
    if not isinstance(value, (dict, types.MappingProxyType)):
        raise _refuse("wrong-type", f"{where} must be a mapping")
    return value


# ---- the operator's plan, gating everything below it --------------------------------------------

def operator_plan(declarations):
    """The six stop fields an operator must pin before any live evaluation -> which are present,
    which are missing, and whether THIS PLAN's own six are complete.

    Absence is `own-declarations-incomplete`, never a default this module fills in and never
    `insufficient-evidence` -- that status describes evidence too thin to score, and an operator
    who has not yet chosen a stopping rule is a planning gap, not a data problem.

    THE SCOPE THIS RETURN VALUE DOES NOT CLAIM. `RECOVERY_REPORT_DECLARATIONS` is six fields, not
    the whole of what a live evaluation needs pinned: `workflow_eval.OPERATOR_DECLARATIONS` names
    seven, and `RECOVERY_PLAN_UNCOVERED_DECLARATIONS` -- `primary_endpoint`, `sample_size` and
    `independent_evaluation` -- are neither declared nor checked here. `own_declarations_complete`
    reporting True and `blocks_promotion_on_these_fields` reporting False describe ONLY this
    plan's own six fields; both are misread as "nothing blocks promotion" if the `not_covered`
    block and `scope_note` below are dropped when this payload is read on its own, which is
    exactly the reading this function's return shape exists to rule out.
    """
    decl = _rr_mapping(declarations, "operator_declarations")
    declared, missing = {}, []
    for name in RECOVERY_REPORT_DECLARATIONS:
        value = decl.get(name)
        declared[name] = _copy(value)
        if value in (None, "", [], {}):
            missing.append(name)
    source = declared.get("independent_label_source")
    if source not in (None, "") and source not in LABEL_SOURCES:
        raise _refuse("unknown-value",
                      f"independent_label_source must be one of {LABEL_SOURCES}, not {source!r}")
    window = declared.get("observation_window")
    if window not in (None, "") and _instant(window) is None:
        raise _refuse("value-invalid", f"observation_window {window!r} names no instant")
    complete = not missing
    return {
        "v": RECOVERY_REPORT_VERSION,
        "fields": list(RECOVERY_REPORT_DECLARATIONS),
        "declared": declared,
        "missing": missing,
        "complete": complete,
        "status": "own-declarations-complete" if complete else "own-declarations-incomplete",
        "blocks_promotion_on_these_fields": not complete,
        "not_covered": {
            "fields": list(RECOVERY_PLAN_UNCOVERED_DECLARATIONS),
            "owner": "workflow_eval.live_requirements",
            "pairs_with": "decision_eval.operator_plan",
            "note": SCOPE_NOTE,
        },
        "scope_note": SCOPE_NOTE,
        "note": None if complete else PLAN_INCOMPLETE_NOTE,
    }


# ---- resources, relayed and checked against the invariants they must still hold -----------------

def _assert_zero_ratio_undefined(accounting, where):
    """Refuse evidence that violates the invariant this report exists to surface: with nothing
    accepted, cost per accepted task is UNDEFINED, never a synthesized zero. This is not a second
    computation of the ratio -- `workflow_eval.arm_accounting` owns that -- it is a refusal to
    relay evidence that no longer agrees with it."""
    accepted = accounting.get("accepted")
    for name, block in (accounting.get("scopes") or {}).items():
        if accepted == 0 and block.get("cost_per_accepted_usd") is not None:
            raise _refuse(
                "value-invalid",
                f"{where}.scopes[{name!r}] reports cost_per_accepted_usd="
                f"{block['cost_per_accepted_usd']!r} with zero accepted; this report refuses to "
                f"relay a ratio that must be undefined")


def _assert_bases_kept_apart(block, where):
    """Refuse a scope block whose totals lost the five-basis structure `workflow_eval` keeps, or
    that smuggled a priced `usd` figure under `proxy` or `unpriced`."""
    totals = block.get("totals") or {}
    missing = sorted(set(RESOURCE_BASES) - set(totals))
    if missing:
        raise _refuse("missing-field",
                      f"{where}.totals is missing basis(es) {missing}; a total that dropped a "
                      f"basis cannot prove the bases stayed separate")
    for basis in ("proxy", "unpriced"):
        if "usd" in (totals.get(basis) or {}):
            raise _refuse(
                "value-invalid",
                f"{where}.totals[{basis!r}] carries a priced 'usd' figure; a subscription-plan "
                f"estimate or an unpriced figure must never be relayed as though it had a price")


def resource_evidence(accountings):
    """Every arm's cohort accounting, exactly as `workflow_eval.arm_accounting` computed it --
    read and copied field for field, never recomputed. See `RESOURCE_EVIDENCE_NOTE`."""
    if not isinstance(accountings, (list, tuple)):
        raise _refuse("wrong-type", "resource_evidence reads a list of arm_accounting() results")
    out = []
    for index, accounting in enumerate(accountings):
        where = f"accountings[{index}]"
        acc = _rr_mapping(accounting, where)
        missing = sorted(set(ACCOUNTING_EVIDENCE_KEYS) - set(acc))
        if missing:
            raise _refuse("missing-field",
                          f"{where} is missing {missing}; this module reads "
                          f"workflow_eval.arm_accounting's own output and fills in none of it")
        _assert_zero_ratio_undefined(acc, where)
        scopes = {}
        for name, raw_block in (acc.get("scopes") or {}).items():
            block = _rr_mapping(raw_block, f"{where}.scopes[{name!r}]")
            block_missing = sorted(set(ACCOUNTING_SCOPE_KEYS) - set(block))
            if block_missing:
                raise _refuse("missing-field",
                              f"{where}.scopes[{name!r}] is missing {block_missing}")
            _assert_bases_kept_apart(block, f"{where}.scopes[{name!r}]")
            scopes[name] = {key: _copy(block[key]) for key in ACCOUNTING_SCOPE_KEYS}
        out.append({
            "arm": acc["arm"], "collapsed_from": list(acc.get("collapsed_from") or []),
            "items": acc["items"], "accepted": acc["accepted"], "failed": acc["failed"],
            "censored": acc["censored"],
            "conditional_recovery": _copy(acc["conditional_recovery"]),
            "initial_attempt": _copy(acc["initial_attempt"]),
            "scopes": scopes, "labels": list(acc.get("labels") or ()),
        })
    return out


# ---- time, by the clock that measured it ---------------------------------------------------------

def time_by_basis(rows):
    """Every duration across many joined rows, grouped by basis and never summed --
    `duration_by_basis` run once per row and merged, so many decisions report the same
    separation this module already guarantees for one."""
    if not isinstance(rows, (list, tuple)):
        raise _refuse("wrong-type", "time_by_basis reads a list of joined rows")
    merged = {basis: [] for basis in _ah().DURATION_BASES}
    for index, row in enumerate(rows):
        if not isinstance(row, (dict, types.MappingProxyType)) or row.get("v") != JOIN_VERSION:
            raise _refuse("wrong-type", f"row[{index}] is not a joined row")
        per_row = duration_by_basis(row)
        for basis, entries in per_row["by_basis"].items():
            merged.setdefault(basis, []).extend(entries)
    return {"by_basis": merged, "note": DURATIONS_SEPARATE}


# ---- subgroup and transfer slices, each just another coverage() call ----------------------------

def slice_coverage(rows, assignments, *, dimension):
    """`coverage()` broken out per named slice of a caller-declared dimension -- one call to this
    module's own `coverage()` per slice, never a second counting pass. A row with no assignment
    is `unassigned`, never dropped."""
    if not isinstance(rows, (list, tuple)):
        raise _refuse("wrong-type", "slice_coverage reads a list of joined rows")
    if not isinstance(assignments, (dict, types.MappingProxyType)):
        raise _refuse("wrong-type",
                      "assignments must map a row's correlation_id to its slice name")
    if not isinstance(dimension, str) or not dimension.strip():
        raise _refuse("wrong-type", "dimension names what the slices split on")
    buckets = {}
    for row in rows:
        name = assignments.get(row.get("correlation_id"), "unassigned")
        buckets.setdefault(name, []).append(row)
    return {
        "dimension": dimension,
        "slices": {name: coverage(members) for name, members in sorted(buckets.items())},
        "note": "a row with no declared assignment is 'unassigned', never dropped",
    }


# ---- every candidate this evaluation tried or rejected, and its exposure ------------------------

def candidate_tally(candidates):
    """Every candidate this evaluation considered, counted by outcome and exposure. A candidate
    that was tried and then rejected stays in the tally -- it is not the same fact as one never
    tried, and its id may not repeat."""
    if not isinstance(candidates, (list, tuple)):
        raise _refuse("wrong-type", "candidate_tally reads a list of candidate records")
    counts = {status: 0 for status in CANDIDATE_STATUSES}
    exposure_total = 0
    exposure_known = 0
    ids = []
    for index, raw in enumerate(candidates):
        record = _rr_mapping(raw, f"candidates[{index}]")
        cid = record.get("id")
        if not isinstance(cid, str) or not cid.strip():
            raise _refuse("wrong-type", f"candidates[{index}].id must be a non-empty string")
        status = record.get("status")
        if status not in CANDIDATE_STATUSES:
            raise _refuse("unknown-value",
                          f"candidates[{index}].status must be one of {CANDIDATE_STATUSES}, not "
                          f"{status!r}")
        counts[status] += 1
        ids.append(cid)
        exposure = record.get("exposure")
        if exposure is not None:
            if not isinstance(exposure, int) or isinstance(exposure, bool) or exposure < 0:
                raise _refuse("wrong-type",
                              f"candidates[{index}].exposure must be a non-negative int or None")
            exposure_total += exposure
            exposure_known += 1
    if len(set(ids)) != len(ids):
        raise _refuse("duplicate-entry", "candidate_tally was handed the same candidate id twice")
    return {
        "counts": counts, "total": len(candidates),
        "exposure_total": exposure_total, "exposure_known": exposure_known,
        "exposure_unknown": len(candidates) - exposure_known,
    }


# ---- quality regression, judged only against the operator's own cap -----------------------------

def quality_regression(baseline, candidate, *, allowed_regression):
    """The paired change in classification quality between two `calibration_report` results,
    judged only against the operator's own declared `allowed_quality_regression` -- never a value
    this module supplies."""
    for report, where in ((baseline, "baseline"), (candidate, "candidate")):
        block = _rr_mapping(report, where)
        if block.get("v") != CALIBRATION_VERSION:
            raise _refuse("wrong-type", f"{where} must be a calibration_report() result")
    b, c = baseline["classification"], candidate["classification"]
    if b["status"] != "computed" or c["status"] != "computed":
        return {
            "v": RECOVERY_REPORT_VERSION, "delta": None, "standard_error": None,
            "baseline": _copy(b), "candidate": _copy(c),
            "allowed_regression": allowed_regression, "verdict": None,
            "verdict_reason": "at least one side has no computed classification metric",
        }
    delta = round(c["value"] - b["value"], 6)
    se = None
    if b.get("standard_error") is not None and c.get("standard_error") is not None:
        se = (b["standard_error"] ** 2 + c["standard_error"] ** 2) ** 0.5
    if allowed_regression is None:
        verdict, reason = None, NO_REGRESSION_CAP_NOTE
    else:
        verdict = (REGRESSION_STATUSES[0] if delta >= -abs(allowed_regression)
                  else REGRESSION_STATUSES[1])
        reason = (f"against the operator's declared allowed_quality_regression "
                 f"{allowed_regression!r}")
    return {
        "v": RECOVERY_REPORT_VERSION, "delta": delta, "standard_error": se,
        "baseline": _copy(b), "candidate": _copy(c), "allowed_regression": allowed_regression,
        "verdict": verdict, "verdict_reason": reason,
    }


# ---- the document -----------------------------------------------------------------------------

def recovery_report(*, provenance, join_document, operator_declarations, calibration=None,
                    regression=None, accountings=(), comparisons=None, slices=None,
                    full_task_study=None, candidates=None, notes=()):
    """One document an operator reads before deciding whether to promote a candidate: quality,
    regression, resources, time, the operator's own plan, coverage, slices and censoring,
    assembled from what existing owners already computed and never recomputed here."""
    if provenance not in DATA_PROVENANCES:
        raise _refuse("unknown-value",
                      f"provenance must be one of {DATA_PROVENANCES}, not {provenance!r}")
    doc = _rr_mapping(join_document, "join_document")
    if doc.get("v") != JOIN_VERSION:
        raise _refuse("wrong-type", "join_document must be the object join() returns")
    plan = operator_plan(operator_declarations)

    quality = None
    if calibration is not None:
        cal = _rr_mapping(calibration, "calibration")
        for field in ("raw", "calibrated"):
            block = cal.get(field)
            if (not isinstance(block, (dict, types.MappingProxyType))
                    or block.get("v") != CALIBRATION_VERSION):
                raise _refuse("wrong-type",
                              f"calibration[{field!r}] must be a calibration_report() result")
        quality = {"raw": _copy(cal["raw"]), "calibrated": _copy(cal["calibrated"])}

    regression_block = None
    if regression is not None:
        reg = _rr_mapping(regression, "regression")
        if reg.get("v") != RECOVERY_REPORT_VERSION:
            raise _refuse("wrong-type",
                          "regression must be the object quality_regression() returns")
        regression_block = _copy(reg)

    comparisons_block = None
    if comparisons is not None:
        if not isinstance(comparisons, (list, tuple)):
            raise _refuse("wrong-type",
                          "comparisons must be the list compare_conditional_recovery() returns")
        comparisons_block = [_copy(_rr_mapping(c, "a comparison row")) for c in comparisons]

    study_block = None
    if full_task_study is not None:
        study = _rr_mapping(full_task_study, "full_task_study")
        if study.get("status") not in ("prospective", "run"):
            raise _refuse("unknown-value",
                          f"full_task_study.status must be 'prospective' or 'run', not "
                          f"{study.get('status')!r}")
        study_block = _copy(study)

    candidates_block = candidate_tally(candidates) if candidates is not None else None
    resources = resource_evidence(accountings)
    coverage_block = _copy(doc.get("coverage")) or {}

    labels = list(notes)
    labels.append(plan["scope_note"])
    if plan["note"]:
        labels.append(plan["note"])
    if provenance == "synthetic":
        labels.append(SYNTHETIC_LABEL)

    report = {
        "v": RECOVERY_REPORT_VERSION,
        "provenance": provenance,
        "operator": plan,
        "quality": quality,
        "regression": regression_block,
        "resources": resources,
        "resources_note": RESOURCE_EVIDENCE_NOTE,
        "comparisons": comparisons_block,
        "time": time_by_basis(list(doc.get("rows") or ())),
        "coverage": coverage_block,
        "censoring": dict(coverage_block.get("censoring") or {}),
        "slices": _copy(slices) if slices is not None else None,
        "candidates": candidates_block,
        "full_task_study": study_block,
        "blocks_promotion_on_these_fields": plan["blocks_promotion_on_these_fields"],
        "labels": labels,
    }
    return assert_no_causal_claim(report)

# END OF D19: OUTCOMES AND STOPPING
