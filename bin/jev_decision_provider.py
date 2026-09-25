#!/usr/bin/env python3
"""Offline Jev-to-decision adapter. No SDK, credential lookup, or network client.

The wire shapes follow https://docs.typesafe.ai/api as inspected for J01. This
module only builds a request body and maps a supplied synthetic response. J01
permits public synthetic data only; a later release must review transport and
any real outbound payload separately.
"""

import importlib.util
import math
import re
from pathlib import Path

PROVIDER = "jev"
DOCUMENTED_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
_LABEL = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_MODS = {}


def _contract():
    if "decision_contract" not in _MODS:
        path = Path(__file__).resolve().parent / "decision_contract.py"
        spec = importlib.util.spec_from_file_location("decision_contract", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _MODS["decision_contract"] = module
    return _MODS["decision_contract"]


def _error(code, message):
    return _contract().ContractError(code, message)


def _label(value, field):
    if not isinstance(value, str) or len(value) > 200 or not _LABEL.fullmatch(value):
        raise _error("value-invalid", f"{field} must be a bounded identifier")
    return value


def _object(value, fields, field):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise _error("value-invalid", f"{field} must have exactly {sorted(fields)}")
    return value


def _probability(value, field):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise _error("value-invalid", f"{field} must be a finite probability")
    if not 0 <= value <= 1:
        raise _error("value-invalid", f"{field} must be between zero and one")
    return float(value)


def _distribution(value, keys, field):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise _error("category-mismatch", f"{field} must cover exactly the declared categories")
    result = {key: _probability(value[key], f"{field}[{key}]") for key in keys}
    if abs(sum(result.values()) - 1) > _contract().DISTRIBUTION_SUM_TOLERANCE:
        raise _error("value-invalid", f"{field} probabilities must sum to one")
    return result


def _request_guard(request):
    if not isinstance(request, _contract().DecisionRequest):
        # bin/ is not a package; another provider may have loaded its own copy
        # of the same contract class. Reparse its public payload instead of
        # confusing module identity with request validity.
        if type(request).__name__ != "DecisionRequest" or not callable(getattr(request, "to_payload", None)):
            raise _error("wrong-type", "Jev requires a parsed DecisionRequest")
        request = _contract().parse_request(request.to_payload())
    if PROVIDER not in request.eligibility["providers"]:
        raise _error("unknown-value", "Jev is not eligible for this request")
    if request.eligibility["privacy"] != "vendor-eligible":
        raise _error("unknown-value", "the request is not vendor-eligible")
    if any(spec.sensitivity != "public" for spec in request.questions):
        raise _error("unknown-value", "J01 accepts public questions only")
    return request


def build_payload(request, *, model, endpoint):
    """Build the documented JSON body; endpoint is validated but never contacted here."""
    request = _request_guard(request)
    _label(model, "model")
    if endpoint != DOCUMENTED_ENDPOINT:
        raise _error("value-invalid", "endpoint must match the documented TypeSafe endpoint")
    questions = {}
    for spec in request.questions:
        item = {"instructions": spec.question}
        if spec.kind == "boolean":
            item["type"] = "noul"
            if spec.rubric:
                item["criteria"] = {"true": spec.rubric["true"],
                                    "false": spec.rubric["false"]}
        elif spec.kind == "choice":
            item.update(type="choice", criteria=dict(spec.rubric))
        elif spec.kind == "ordinal":
            if len(spec.outcomes) > 10:
                raise _error("unknown-value", "Jev Score supports at most ten levels")
            item.update(type="score", criteria=[spec.rubric[key] for key in spec.outcomes])
        else:
            raise _error("unknown-value", "unsupported question kind")
        questions[spec.qualified_id] = item
    return {"state": dict(request.state), "model": model, "questions": questions}


def map_response(request, response, *, model, endpoint):
    """Map one synthetic/documented response to the V1 payload, then validate it."""
    request = _request_guard(request)
    build_payload(request, model=model, endpoint=endpoint)
    data = _object(response, ("model", "answers", "usage"), "Jev response")
    _label(data["model"], "response.model")
    if not isinstance(data["usage"], dict) or set(data["usage"]) != {"input_tokens", "output_tokens"}:
        raise _error("value-invalid", "response.usage must contain input_tokens and output_tokens")
    if any(isinstance(n, bool) or not isinstance(n, int) or n < 0 for n in data["usage"].values()):
        raise _error("value-invalid", "response.usage token counts must be nonnegative integers")
    specs = request.question_by_qualified_id()
    if not isinstance(data["answers"], dict) or set(data["answers"]) != set(specs):
        raise _error("missing-answer", "Jev answers must match all requested question ids")
    answers = {}
    for qid, spec in specs.items():
        answer = data["answers"][qid]
        if spec.kind == "boolean":
            answer = _object(answer, ("type", "noul"), qid)
            if answer["type"] != "noul":
                raise _error("unknown-value", f"{qid} must be a Noul answer")
            yes = _probability(answer["noul"], f"{qid}.noul")
            raw = {"false": 1 - yes, "true": yes}
            outcome = "true" if yes > 0.5 else "false"
            confidence = None  # Noul has no separate vendor confidence.
        elif spec.kind == "choice":
            answer = _object(answer, ("type", "choice", "probabilities", "confidence"), qid)
            if answer["type"] != "choice":
                raise _error("unknown-value", f"{qid} must be a Choice answer")
            raw = _distribution(answer["probabilities"], spec.outcomes, f"{qid}.probabilities")
            selected = answer["choice"]
            if selected not in spec.outcomes or raw[selected] != max(raw.values()):
                raise _error("value-invalid", f"{qid}.choice is not a maximum-probability option")
            outcome = max(spec.outcomes, key=lambda key: raw[key])
            confidence = _probability(answer["confidence"], f"{qid}.confidence")
        else:
            answer = _object(answer, ("type", "score", "legend", "probabilities", "confidence"), qid)
            if answer["type"] != "score":
                raise _error("unknown-value", f"{qid} must be a Score answer")
            indices = [str(i) for i in range(len(spec.outcomes))]
            expected_legend = {index: spec.rubric[key] for index, key in zip(indices, spec.outcomes)}
            if answer["legend"] != expected_legend:
                raise _error("category-mismatch", f"{qid}.legend differs from the question rubric")
            indexed = _distribution(answer["probabilities"], indices, f"{qid}.probabilities")
            score = answer["score"]
            if isinstance(score, bool) or not isinstance(score, (float, int)) or not math.isfinite(score):
                raise _error("value-invalid", f"{qid}.score must be finite")
            if not 0 <= score <= len(indices) - 1:
                raise _error("value-invalid", f"{qid}.score is out of range")
            if abs(score - sum(i * indexed[str(i)] for i in range(len(indices)))) > 1e-6:
                raise _error("value-invalid", f"{qid}.score disagrees with probabilities")
            raw = {key: indexed[str(i)] for i, key in enumerate(spec.outcomes)}
            outcome = spec.outcomes[max(range(len(indices)), key=lambda i: indexed[str(i)])]
            confidence = _probability(answer["confidence"], f"{qid}.confidence")
        answers[qid] = {"outcome": outcome, "abstained": False, "raw": raw,
                        "calibrated": None, "vendor_confidence": confidence}
    payload = {
        "v": _contract().CONTRACT_VERSION, "correlation_id": request.correlation_id,
        "state_sha": request.state_sha, "questions_sha": request.questions_sha,
        "status": "ok", "answers": answers, "recommended": None, "evidence_refs": [],
        "requested_provider": PROVIDER, "dispatched_provider": None,
        "observed_provider": None, "requested_model": model,
        "dispatched_model": None, "observed_model": None,
        "provider_contract_v": None, "duration": None, "usage": None,
        "note": None,
    }
    _contract().parse_result(payload, request)
    return payload


def evaluate(request, *, model, endpoint, synthetic_response):
    """Map a caller-supplied synthetic fixture; there is no transport parameter."""
    if synthetic_response is None:
        raise _error("missing-field", "a synthetic response is required")
    return map_response(request, synthetic_response, model=model, endpoint=endpoint)
