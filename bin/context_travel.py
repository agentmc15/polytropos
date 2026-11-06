"""Pure, bounded context-travel data contract. A digest identifies bytes, not authority."""

import hashlib
import copy
import importlib.util
import json
import math
import re
from pathlib import Path


def _sibling(name):
    """Load a bin/ sibling without depending on the caller's sys.path."""
    path = Path(__file__).resolve().parent / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


attempt_ledger = _sibling("attempt_ledger")
redact = _sibling("redact")


CONTRACT_VERSION = "polytropos.context-travel/1"
MAX_BYTES = 32768
MAX_TEXT = 2000
MAX_ID = 200
MAX_ITEMS = 32
SHA = re.compile(r"[0-9a-f]{64}\Z")


class ContractError(ValueError):
    """Invalid or uncorrelated context-travel data."""


def _json_value(value, depth=0):
    if depth > 12:
        raise ContractError("JSON nesting exceeds limit")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError("nonfinite number")
        return
    if isinstance(value, list):
        if len(value) > MAX_ITEMS:
            raise ContractError("JSON array exceeds limit")
        for item in value:
            _json_value(item, depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > MAX_ITEMS or any(not isinstance(k, str) for k in value):
            raise ContractError("invalid JSON object")
        for item in value.values():
            _json_value(item, depth + 1)
        return
    raise ContractError("non-JSON value")


def canonical_bytes(value):
    """UTF-8 JSON: sorted object keys, compact separators, ordered arrays, no NaN."""
    _json_value(value)
    try:
        result = json.dumps(value, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (UnicodeError, ValueError, TypeError) as exc:
        raise ContractError("invalid JSON encoding") from exc
    if len(result) > MAX_BYTES:
        raise ContractError("payload exceeds byte limit")
    return result


def content_sha(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("duplicate JSON key")
        result[key] = value
    return result


def _bad_constant(value):
    raise ContractError("nonfinite JSON constant")


def _load(raw):
    if not isinstance(raw, (str, bytes)):
        raise ContractError("JSON input must be text or bytes")
    try:
        data = raw.encode("utf-8") if isinstance(raw, str) else raw
        if len(data) > MAX_BYTES:
            raise ContractError("payload exceeds byte limit")
        result = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs,
                            parse_constant=_bad_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ContractError("invalid JSON payload") from exc
    canonical_bytes(result)
    return result


def _keys(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        raise ContractError("unexpected or missing fields")


def _identifier(value, label):
    if (type(value) is not str or not value or len(value) > MAX_ID
            or value != value.strip() or any(ord(c) < 32 for c in value)
            or redact.scan(value)):
        raise ContractError("invalid " + label)
    return value


def _relative_path(value, label):
    _identifier(value, label)
    if (value.startswith("/") or "\\" in value or ":" in value
            or any(part in ("", ".", "..") for part in value.split("/"))):
        raise ContractError("unsafe " + label)
    return value


def _sha(value, label):
    if type(value) is not str or not SHA.fullmatch(value):
        raise ContractError("invalid " + label)


def make_task_identity(repository_id, kit_path, task_id):
    """Stable identity; checkout and revision are deliberately excluded."""
    _identifier(repository_id, "repository ID")
    _relative_path(kit_path, "kit path")
    _identifier(task_id, "task ID")
    return "sha256:" + content_sha([repository_id, kit_path, task_id])


REQUEST_FIELDS = ("v", "repository_id", "checkout_id", "revision", "source_state_ref",
                  "kit_path", "task_id", "task_identity", "assignment_id", "assignment_role",
                  "question", "acceptance_ref", "source_ref", "request_sha")
def _validate_request(value):
    _keys(value, REQUEST_FIELDS)
    if value["v"] != CONTRACT_VERSION:
        raise ContractError("unknown request version")
    for name in ("repository_id", "checkout_id", "task_id", "assignment_id", "assignment_role"):
        _identifier(value[name], name)
    _validate_text(value["question"])
    for name in ("source_state_ref", "acceptance_ref", "source_ref"):
        _ref(value[name])
    _relative_path(value["kit_path"], "kit_path")
    if value["revision"] is not None:
        _identifier(value["revision"], "revision")
    if value["task_identity"] != make_task_identity(value["repository_id"],
                                                    value["kit_path"], value["task_id"]):
        raise ContractError("task identity mismatch")
    _sha(value["request_sha"], "request digest")
    if value["request_sha"] != content_sha({k: v for k, v in value.items()
                                             if k != "request_sha"}):
        raise ContractError("request digest mismatch")
    canonical_bytes(value)
    return value


def make_request(repository_id, checkout_id, revision, kit_path, task_id, assignment_id,
                 assignment_role, question, *, source_state_ref=None, acceptance_ref=None,
                 source_ref=None):
    value = {"v": CONTRACT_VERSION, "repository_id": repository_id,
             "checkout_id": checkout_id, "revision": revision, "kit_path": kit_path,
             "task_id": task_id, "task_identity": make_task_identity(repository_id, kit_path, task_id),
             "assignment_id": assignment_id, "assignment_role": assignment_role,
             "question": _text(question), "source_state_ref": _ref(source_state_ref),
             "acceptance_ref": _ref(acceptance_ref), "source_ref": _ref(source_ref)}
    value["request_sha"] = content_sha(value)
    return _validate_request(value)


def parse_request(raw):
    return _validate_request(_load(raw))


def _text(value):
    if type(value) is not str or len(value) > MAX_TEXT:
        raise ContractError("text exceeds limit or is not a string")
    outcome = redact.redact(value, limit=None)
    if len(outcome["text"]) > MAX_TEXT:
        raise ContractError("redacted text exceeds limit")
    return {"text": outcome["text"], "redactions": outcome["redactions"]}


def _validate_text(value):
    _keys(value, ("text", "redactions"))
    if type(value["text"]) is not str or len(value["text"]) > MAX_TEXT:
        raise ContractError("invalid text")
    counts = value["redactions"]
    if type(counts) is not dict or len(counts) > len(redact.PATTERNS):
        raise ContractError("invalid redaction counts")
    kinds = {kind for kind, _ in redact.PATTERNS}
    if any(k not in kinds or type(v) is not int or v < 1 or v > MAX_TEXT
           for k, v in counts.items()):
        raise ContractError("invalid redaction counts")
    if redact.scan(value["text"]):
        raise ContractError("unredacted credential shape in text")


def _ref(value):
    if value is None:
        return None
    _keys(value, attempt_ledger.REF_FIELDS)
    for name in attempt_ledger.REF_FIELDS:
        part = value[name]
        if part is not None:
            _identifier(part, "reference " + name)
    if value["id"] is None:
        raise ContractError("reference ID missing")
    if value["sha"] is not None:
        _sha(value["sha"], "reference digest")
    try:
        return attempt_ledger.make_ref(value["id"], value["sha"], value["v"])
    except attempt_ledger.RefError as exc:
        raise ContractError("invalid reference") from exc


BRIEF_FIELDS = REQUEST_FIELDS + ("summary", "criteria", "evidence", "provenance",
                                  "declared_freshness", "content_sha")


def _validate_briefing(request, value):
    _validate_request(request)
    _keys(value, BRIEF_FIELDS)
    if any(value[k] != request[k] for k in REQUEST_FIELDS):
        raise ContractError("briefing does not match request")
    _validate_text(value["summary"])
    criteria = value["criteria"]
    if type(criteria) is not list or not 1 <= len(criteria) <= MAX_ITEMS:
        raise ContractError("invalid criteria")
    for item in criteria:
        _validate_text(item)
    evidence = value["evidence"]
    if type(evidence) is not list or len(evidence) > MAX_ITEMS:
        raise ContractError("invalid evidence")
    for item in evidence:
        _keys(item, ("kind", "ref", "note"))
        if item["kind"] not in ("source", "evidence"):
            raise ContractError("invalid evidence kind")
        _ref(item["ref"])
        _validate_text(item["note"])
    _keys(value["provenance"], attempt_ledger.PROVENANCE_REFS)
    for ref in value["provenance"].values():
        _ref(ref)
    if value["declared_freshness"] not in ("unknown", "current", "stale"):
        raise ContractError("invalid declared freshness")
    _sha(value["content_sha"], "briefing digest")
    if value["content_sha"] != content_sha({k: v for k, v in value.items()
                                             if k != "content_sha"}):
        raise ContractError("briefing digest mismatch")
    canonical_bytes(value)
    return value


def make_briefing(request, summary, criteria, evidence=(), provenance=None,
                  declared_freshness="unknown"):
    _validate_request(request)
    if type(criteria) not in (list, tuple) or not 1 <= len(criteria) <= MAX_ITEMS:
        raise ContractError("invalid criteria")
    if type(evidence) not in (list, tuple) or len(evidence) > MAX_ITEMS:
        raise ContractError("invalid evidence")
    provenance = dict.fromkeys(attempt_ledger.PROVENANCE_REFS) if provenance is None else provenance
    _keys(provenance, attempt_ledger.PROVENANCE_REFS)
    bounded_evidence = []
    for item in evidence:
        _keys(item, ("kind", "ref", "note"))
        bounded_evidence.append({"kind": item["kind"], "ref": _ref(item["ref"]),
                                 "note": _text(item["note"])})
    value = {**copy.deepcopy(request), "summary": _text(summary),
             "criteria": [_text(item) for item in criteria],
             "evidence": bounded_evidence,
             "provenance": {k: _ref(v) for k, v in provenance.items()},
             "declared_freshness": declared_freshness}
    value["content_sha"] = content_sha(value)
    return _validate_briefing(request, value)


def parse_briefing(request, raw):
    return _validate_briefing(request, _load(raw))
