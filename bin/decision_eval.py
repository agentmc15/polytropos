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
    there is no field here that could hold one.

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
        "actions": {
            "baseline": rec["baseline"] if rec else None,
            "recommended": (res or {}).get("recommended"),
            "taken": taken,
            "outcome": _copy(outcome),
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
