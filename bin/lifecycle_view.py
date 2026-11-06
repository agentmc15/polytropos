"""CT3: pure advisory lifecycle projections from CT1 requests and CT2 observations."""

import copy
import hashlib
import importlib.util
import json
import math
import re
from pathlib import Path


CONTRACT_VERSION = "polytropos.lifecycle-view/1"
ROLES = ("architect", "implementer", "verifier", "reviewer")
MAX_BYTES = 32768
MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_LINKS = 16
MAX_FINDINGS = 128


class ViewError(ValueError):
    """Malformed, mismatched, or unrepresentable lifecycle view."""


def _sibling(name):
    path = Path(__file__).resolve().with_name(name + ".py")
    spec = importlib.util.spec_from_file_location("lifecycle_view_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Load siblings before runtime operations so composing a view never opens a file.
_ct = _sibling("context_travel")
_kit = _sibling("kit_contract")
_redact = _sibling("redact")
_readers = _sibling("context_readers")


def _bounded_json(value, *, ceiling=MAX_BYTES):
    def walk(item, depth=0):
        if depth > 14:
            raise ViewError("JSON nesting exceeds limit")
        if item is None or type(item) in (str, bool, int):
            return
        if type(item) is float:
            if not math.isfinite(item):
                raise ViewError("nonfinite number")
            return
        if type(item) is list:
            if len(item) > MAX_FINDINGS:
                raise ViewError("collection exceeds limit")
            for child in item:
                walk(child, depth + 1)
            return
        if type(item) is dict:
            if len(item) > MAX_FINDINGS or any(type(key) is not str for key in item):
                raise ViewError("invalid JSON object")
            for child in item.values():
                walk(child, depth + 1)
            return
        raise ViewError("non-JSON value")

    walk(value)
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ViewError("invalid JSON value") from None
    if len(raw) > ceiling:
        raise ViewError("payload exceeds limit")
    return raw


def canonical_bytes(value):
    """Canonical UTF-8 JSON for one bounded lifecycle-view object."""
    return _bounded_json(value)


def _sha(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ViewError("duplicate JSON key")
        out[key] = value
    return out


def _nonfinite(_value):
    raise ViewError("nonfinite JSON number")


def _keys(value, names):
    if type(value) is not dict or set(value) != set(names):
        raise ViewError("unexpected or missing fields")


def _request(value):
    try:
        return _ct.parse_request(_ct.canonical_bytes(value))
    except (ValueError, TypeError, RecursionError):
        raise ViewError("invalid CT1 request") from None


def _subject(request):
    return {name: copy.deepcopy(request[name]) for name in
            ("repository_id", "kit_path", "task_id", "task_identity", "checkout_id",
             "revision", "source_state_ref")}


def _basis(ref=None, selector=None, missing=None):
    return {"source_ref": copy.deepcopy(ref), "selector": selector,
            "missing_basis_code": missing if ref is None else None}


def _text(value, counts=None):
    result = _redact.redact(str(value), limit=None)
    if counts is not None:
        for kind, amount in result["redactions"].items():
            counts[kind] = counts.get(kind, 0) + amount
    return result["text"]


def _ref(value, required=False):
    if value is None and required:
        raise ViewError("required reference missing")
    try:
        return _ct._ref(value)
    except (ValueError, TypeError):
        raise ViewError("invalid reference") from None


def _source_report(sources, request):
    if type(sources) is not dict:
        raise ViewError("invalid source report")
    _bounded_json(sources, ceiling=MAX_INPUT_BYTES)
    _keys(sources, ("v", "subject", "sources", "reads", "coverage", "limits"))
    if sources["v"] != _readers.CONTRACT_VERSION or sources["subject"] != {
            "repository_id": request["repository_id"], "kit_path": request["kit_path"]}:
        raise ViewError("source subject mismatch")
    entries = sources["sources"]
    if type(entries) is not list or len(entries) > 16:
        raise ViewError("invalid source inventory")
    reads = sources["reads"]
    _keys(reads, ("selected", "opened", "bytes"))
    if any(type(value) is not int or value < 0 for value in reads.values()):
        raise ViewError("invalid read accounting")
    coverage = sources["coverage"]
    _keys(coverage, ("complete", "stopped_by", "absent"))
    if type(coverage["complete"]) is not bool or type(coverage["absent"]) is not list:
        raise ViewError("invalid source coverage")
    if (coverage["stopped_by"] not in (None, "max_sources")
            or len(coverage["absent"]) > 2
            or any(kind not in ("graph", "attempt-events") for kind in coverage["absent"])):
        raise ViewError("invalid source coverage")
    _keys(sources["limits"], _readers.DEFAULT_LIMITS)
    for name, ceiling in _readers.LIMIT_CEILINGS.items():
        value = sources["limits"][name]
        if type(value) is not int or not 1 <= value <= ceiling:
            raise ViewError("invalid source limit")
    if reads["selected"] != len(entries) or reads["selected"] > sources["limits"]["max_sources"] \
            or reads["bytes"] > sources["limits"]["max_total_bytes"]:
        raise ViewError("invalid source accounting")
    seen = set()
    for item in entries:
        _keys(item, ("kind", "state", "ref", "observed", "freshness", "consistency",
                     "coverage", "redactions", "exclusions", "reason_code"))
        if (type(item["kind"]) is not str or item["kind"] in seen
                or item["kind"] not in ("graph", "attempt-events") +
                    tuple("kit:" + name for name in _readers.KIT_FILES)):
            raise ViewError("invalid source kind")
        seen.add(item["kind"])
        if item["state"] not in ("ok", "missing", "forbidden", "corrupt",
                                 "inconsistent", "over-limit", "unavailable"):
            raise ViewError("invalid source state")
        _ref(item["ref"])
        if item["consistency"] not in ("unknown", "consistent-at-read"):
            raise ViewError("invalid source consistency")
        _keys(item["freshness"], ("state", "basis"))
        if item["freshness"] != {"state": "unknown", "basis": "not-assessed"}:
            raise ViewError("invalid source freshness")
        _keys(item["coverage"], ("complete", "items", "retained_bytes"))
        cov = item["coverage"]
        if (type(cov["complete"]) is not bool or
                any(type(cov[key]) is not int or cov[key] < 0 for key in ("items", "retained_bytes"))
                or cov["items"] > sources["limits"]["max_items"]
                or cov["retained_bytes"] > sources["limits"]["max_source_bytes"]):
            raise ViewError("invalid source coverage")
        if cov["complete"] != (item["state"] == "ok" and not item["exclusions"]):
            raise ViewError("inconsistent source coverage")
        if type(item["redactions"]) is not dict or type(item["exclusions"]) is not dict:
            raise ViewError("invalid source counts")
        kinds = {kind for kind, _ in _redact.PATTERNS}
        if any(k not in kinds or type(v) is not int or v < 1
               for k, v in item["redactions"].items()):
            raise ViewError("invalid source redactions")
        if any(type(k) is not str or len(k) > 80 or type(v) is not int or v < 1
               for k, v in item["exclusions"].items()):
            raise ViewError("invalid source exclusions")
        if item["reason_code"] is not None and (type(item["reason_code"]) is not str
                                                  or len(item["reason_code"]) > 80):
            raise ViewError("invalid source reason")
        if item["state"] == "ok":
            if item["ref"] is None or item["consistency"] != "consistent-at-read":
                raise ViewError("invalid observed source")
            observed = item["observed"]
            if item["kind"] == "kit:TASKS.md":
                if type(observed) is not list or any(type(task) is not dict for task in observed):
                    raise ViewError("invalid task observation")
                for task in observed:
                    _keys(task, ("id", "title", "status", "model", "depends", "independent",
                                 "evidence", "brief", "acceptance", "verify"))
                    if (type(task["id"]) is not str or type(task["title"]) is not str
                            or task["status"] not in _kit.STATUSES
                            or type(task["depends"]) is not list
                            or any(type(dep) is not str for dep in task["depends"])
                            or type(task["independent"]) is not bool
                            or type(task["brief"]) is not str
                            or type(task["acceptance"]) is not str
                            or task["verify"] is not None and type(task["verify"]) is not str):
                        raise ViewError("invalid task observation")
                    try:
                        _ct._identifier(task["id"], "task ID")
                        for dep in task["depends"]:
                            _ct._identifier(dep, "dependency ID")
                    except ValueError:
                        raise ViewError("invalid task identity") from None
            elif item["kind"] == "kit:NOTES.md":
                _keys(observed, ("text",))
                if type(observed["text"]) is not str:
                    raise ViewError("invalid notes observation")
            elif item["kind"] == "graph":
                _keys(observed, ("nodes", "links"))
                if type(observed["nodes"]) is not list or type(observed["links"]) is not list \
                        or any(type(v) is not dict for v in observed["nodes"] + observed["links"]):
                    raise ViewError("invalid graph observation")
                for node in observed["nodes"]:
                    if not set(node).issubset({"id", "label", "name", "source_file"}):
                        raise ViewError("invalid graph node fields")
                    if "id" in node and type(node["id"]) not in (str, int):
                        raise ViewError("invalid graph node id")
                    if any(node.get(k) is not None and type(node[k]) is not str
                           for k in ("label", "name", "source_file")):
                        raise ViewError("invalid graph node text")
                for edge in observed["links"]:
                    if not set(edge).issubset({"source", "target", "relation"}) \
                            or any(k not in edge or type(edge[k]) not in (str, int)
                                   for k in ("source", "target")) \
                            or edge.get("relation") is not None and type(edge["relation"]) is not str:
                        raise ViewError("invalid graph edge")
            elif item["kind"] == "attempt-events":
                if type(observed) is not list or any(type(ev) is not dict for ev in observed):
                    raise ViewError("invalid event observation")
                for event in observed:
                    if type(event.get("kind")) is not str or type(event.get("v")) is not str:
                        raise ViewError("invalid event identity")
                    for key in ("task", "run", "attempt", "repository_id", "kit_path", "status"):
                        if key in event and event[key] is not None and type(event[key]) is not str:
                            raise ViewError("invalid event correlation")
                    if "rc" in event and event["rc"] is not None and type(event["rc"]) is not int:
                        raise ViewError("invalid event result")
                    if "tautological" in event and type(event["tautological"]) is not bool:
                        raise ViewError("invalid precheck")
                    if "acceptance_ref" in event:
                        _ref(event["acceptance_ref"])
            else:
                _keys(observed, ("text",))
                if type(observed["text"]) is not str:
                    raise ViewError("invalid text observation")
        elif item["observed"] is not None:
            raise ViewError("failed source carries observed data")
    return sources


def _links(values, request, kind):
    if type(values) not in (list, tuple) or len(values) > MAX_LINKS:
        raise ViewError("invalid link collection")
    out, seen = [], set()
    for value in values:
        fields = {"subject", "ref", "epistemic"}
        if kind == "intent":
            fields.add("kind")
        if kind == "dependency":
            fields.add("state")
        _keys(value, fields)
        subject = value["subject"]
        _keys(subject, ("repository_id", "kit_path", "task_id"))
        if subject["repository_id"] != request["repository_id"] or subject["kit_path"] != request["kit_path"]:
            raise ViewError("link subject mismatch")
        try:
            _ct._identifier(subject["task_id"], "task ID")
        except ValueError:
            raise ViewError("invalid link task") from None
        if kind != "dependency" and subject["task_id"] != request["task_id"]:
            raise ViewError("link task mismatch")
        if value["epistemic"] != "caller-declared":
            raise ViewError("invalid link epistemic")
        ref = _ref(value["ref"], required=kind != "dependency" or value.get("state") != "unknown")
        if kind == "intent" and value["kind"] not in ("goal", "requirement", "outcome"):
            raise ViewError("invalid intent kind")
        if kind == "dependency" and value["state"] not in ("fresh", "stale", "unknown"):
            raise ViewError("invalid dependency state")
        key = subject["task_id"] if kind != "intent" else (subject["task_id"], value["kind"])
        if key in seen:
            raise ViewError("duplicate link")
        seen.add(key)
        out.append({**copy.deepcopy(value), "ref": ref})
    return out


def _view_digest(view):
    return _sha({key: value for key, value in view.items() if key != "content_sha"})


def _check_text(value, *, nullable=False):
    if value is None and nullable:
        return
    if type(value) is not str or len(value) > MAX_BYTES or _redact.scan(value):
        raise ViewError("invalid view text")


def _check_basis(values):
    if type(values) is not list or not 1 <= len(values) <= MAX_LINKS:
        raise ViewError("invalid finding basis")
    for value in values:
        _keys(value, ("source_ref", "selector", "missing_basis_code"))
        ref = _ref(value["source_ref"])
        if value["selector"] is not None:
            _check_text(value["selector"])
        if ref is None:
            if type(value["missing_basis_code"]) is not str or not value["missing_basis_code"]:
                raise ViewError("missing basis code required")
            _check_text(value["missing_basis_code"])
        elif value["missing_basis_code"] is not None:
            raise ViewError("unexpected missing basis code")


def _check_limitation(value):
    _keys(value, ("code", "detail", "critical", "basis"))
    _check_text(value["code"])
    _check_text(value["detail"])
    if type(value["critical"]) is not bool:
        raise ViewError("invalid limitation critical flag")
    _check_basis(value["basis"])


def _check_finding(value):
    _keys(value, ("id", "kind", "claim", "epistemic", "applicability", "basis", "critical"))
    for key in ("id", "kind", "claim"):
        _check_text(value[key])
    if (not value["id"].startswith("f") or not value["id"][1:].isdigit()
            or value["epistemic"] not in ("recorded", "caller-declared", "inferred", "unknown")
            or value["applicability"] not in ("subject-matched", "caller-declared", "unbound", "mismatch")
            or type(value["critical"]) is not bool):
        raise ViewError("invalid finding")
    _check_basis(value["basis"])


def _check_relationship(value):
    _keys(value, ("kind", "from", "to", "epistemic", "basis"))
    if value["kind"] not in ("declared-dependency", "code-navigation", "task-path-mention",
                             "measured-verification", "recorded-outcome"):
        raise ViewError("invalid relationship kind")
    if value["epistemic"] not in ("recorded", "caller-declared", "inferred", "unknown"):
        raise ViewError("invalid relationship epistemic")
    _check_text(value["from"])
    _check_text(value["to"])
    _check_basis(value["basis"])


def _check_source_state(value):
    _keys(value, ("kind", "state", "ref", "consistency", "freshness", "redactions"))
    _check_text(value["kind"])
    if value["state"] not in ("ok", "missing", "forbidden", "corrupt", "inconsistent",
                              "over-limit", "unavailable"):
        raise ViewError("invalid source state")
    _ref(value["ref"])
    if value["consistency"] not in ("unknown", "consistent-at-read"):
        raise ViewError("invalid consistency")
    _keys(value["freshness"], ("state", "basis"))
    if value["freshness"] != {"state": "unknown", "basis": "not-assessed"}:
        raise ViewError("invalid freshness")
    if type(value["redactions"]) is not dict or any(
            k not in {kind for kind, _ in _redact.PATTERNS} or type(v) is not int or v < 1
            for k, v in value["redactions"].items()):
        raise ViewError("invalid redactions")


def _validate_view(view):
    if type(view) is not dict or view.get("v") != CONTRACT_VERSION:
        raise ViewError("unknown view version")
    kind = view.get("kind")
    if kind == "projection":
        _keys(view, ("v", "kind", "status", "request", "subject", "overview", "brief",
                     "findings", "relationships", "limitations", "content_sha"))
        request = _request(view["request"])
        if view["subject"] != _subject(request):
            raise ViewError("view subject mismatch")
        overview = view["overview"]
        _keys(overview, ("task_status", "task_title", "source_states", "coverage_complete",
                         "redactions"))
        if overview["task_status"] is not None and overview["task_status"] not in _kit.STATUSES:
            raise ViewError("invalid task status")
        _check_text(overview["task_title"], nullable=True)
        if type(overview["coverage_complete"]) is not bool or type(overview["source_states"]) is not list:
            raise ViewError("invalid overview")
        if len(overview["source_states"]) > 16:
            raise ViewError("source inventory exceeds limit")
        for source in overview["source_states"]:
            _check_source_state(source)
        if type(overview["redactions"]) is not dict or any(
                k not in {kind for kind, _ in _redact.PATTERNS} or type(v) is not int or v < 1
                for k, v in overview["redactions"].items()):
            raise ViewError("invalid overview redactions")
        if view["status"] not in ("complete", "partial", "refused"):
            raise ViewError("invalid view status")
        if (type(view["findings"]) is not list or type(view["relationships"]) is not list
                or type(view["limitations"]) is not list
                or any(len(view[key]) > MAX_FINDINGS for key in ("findings", "relationships", "limitations"))):
            raise ViewError("invalid view collections")
        for item in view["findings"]:
            _check_finding(item)
        for item in view["relationships"]:
            _check_relationship(item)
        for item in view["limitations"]:
            _check_limitation(item)
        if [item["id"] for item in view["findings"]] != ["f" + str(i + 1)
                                                        for i in range(len(view["findings"]))]:
            raise ViewError("finding IDs are not sequential")
        if view["status"] == "refused":
            if view["brief"] is not None:
                raise ViewError("refused view has brief")
        else:
            brief = view["brief"]
            _keys(brief, ("role", "summary", "criteria_text", "focus", "critical_limitations"))
            if brief["role"] != request["assignment_role"] or brief["role"] not in ROLES:
                raise ViewError("brief role mismatch")
            _check_text(brief["summary"], nullable=True)
            _check_text(brief["criteria_text"], nullable=True)
            if type(brief["focus"]) is not list or any(type(fid) is not str for fid in brief["focus"]):
                raise ViewError("invalid brief focus")
            if len(brief["focus"]) != len(view["findings"]) \
                    or set(brief["focus"]) != {item["id"] for item in view["findings"]}:
                raise ViewError("brief focus omits findings")
            if type(brief["critical_limitations"]) is not list:
                raise ViewError("invalid brief limitations")
            if brief["critical_limitations"] != [item for item in view["limitations"]
                                                 if item["critical"]]:
                raise ViewError("critical limitations missing from brief")
            if brief["criteria_text"] is None or brief["criteria_text"] == "":
                if not any(item["code"] in ("criteria-missing", "task-unavailable") and
                           item["critical"] for item in view["limitations"]):
                    raise ViewError("missing criteria lack limitation")
            if overview["task_status"] is None and brief["criteria_text"] is not None:
                raise ViewError("criteria without selected task")
            if view["status"] == "complete" and (
                    brief["criteria_text"] is None or any(item["critical"] for item in view["limitations"])):
                raise ViewError("complete view has unresolved mandatory context")
    elif kind == "comparison":
        _keys(view, ("v", "kind", "subject", "before_sha", "after_sha",
                     "applicability_changes", "changes", "limitations", "content_sha"))
        if any(type(view[k]) is not str or re.fullmatch(r"[0-9a-f]{64}", view[k]) is None
               for k in ("before_sha", "after_sha")):
            raise ViewError("invalid comparison reference")
        if type(view["changes"]) is not list or type(view["applicability_changes"]) is not list:
            raise ViewError("invalid comparison collections")
        _keys(view["subject"], ("repository_id", "kit_path", "task_identity"))
        try:
            _ct._identifier(view["subject"]["repository_id"], "repository ID")
            _ct._relative_path(view["subject"]["kit_path"], "kit path")
        except ValueError:
            raise ViewError("invalid comparison subject") from None
        identity = view["subject"]["task_identity"]
        if type(identity) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", identity) is None:
            raise ViewError("invalid comparison subject")
        if len(view["changes"]) > MAX_FINDINGS or len(view["applicability_changes"]) > 3:
            raise ViewError("comparison collection exceeds limit")
        for item in view["applicability_changes"]:
            _keys(item, ("field", "before", "after"))
            if item["field"] not in ("checkout_id", "revision", "source_state_ref"):
                raise ViewError("invalid applicability delta")
            if item["field"] == "source_state_ref":
                _ref(item["before"])
                _ref(item["after"])
            else:
                for value in (item["before"], item["after"]):
                    if item["field"] == "revision" and value is None:
                        continue
                    try:
                        _ct._identifier(value, item["field"])
                    except ValueError:
                        raise ViewError("invalid applicability value") from None
        for item in view["changes"]:
            _keys(item, ("field", "before", "after", "epistemic"))
            field = item["field"]
            if field not in ("view-status", "task-status", "criteria-text", "acceptance-ref",
                             "source-states", "findings", "limitations"):
                raise ViewError("unknown comparison field")
            if item["epistemic"] != "observed-change-not-proof":
                raise ViewError("invalid comparison epistemic")
            for value in (item["before"], item["after"]):
                if field == "view-status":
                    if value not in ("complete", "partial", "refused"):
                        raise ViewError("invalid compared status")
                elif field == "task-status":
                    if value is not None and value not in _kit.STATUSES:
                        raise ViewError("invalid compared task status")
                elif field == "criteria-text":
                    _check_text(value, nullable=True)
                elif field == "acceptance-ref":
                    _ref(value)
                else:
                    if type(value) is not list or len(value) > MAX_FINDINGS:
                        raise ViewError("invalid compared collection")
                    checker = {"source-states": _check_source_state,
                               "findings": _check_finding,
                               "limitations": _check_limitation}[field]
                    for element in value:
                        checker(element)
        if type(view["limitations"]) is not list:
            raise ViewError("invalid comparison limitations")
        for item in view["limitations"]:
            _check_limitation(item)
    else:
        raise ViewError("unknown view kind")
    if type(view["content_sha"]) is not str or view["content_sha"] != _view_digest(view):
        raise ViewError("view digest mismatch")
    canonical_bytes(view)
    return view


def parse_view(raw):
    """Strictly parse and validate a projection or comparison, including its digest."""
    if type(raw) not in (str, bytes):
        raise ViewError("view JSON must be text or bytes")
    try:
        data = raw.encode("utf-8") if type(raw) is str else raw
        if len(data) > MAX_BYTES:
            raise ViewError("payload exceeds limit")
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=_nonfinite)
    except (ValueError, UnicodeError, RecursionError):
        raise ViewError("invalid view JSON") from None
    return _validate_view(value)


def compose_view(request, sources, *, role, intent_links=(), acceptance_links=(),
                 dependency_freshness=(), max_bytes=MAX_BYTES):
    """Project supplied facts and uncertainty; never decide readiness or acceptance."""
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES:
        raise ViewError("invalid output budget")
    req = _request(request)
    if role not in ROLES or role != req["assignment_role"]:
        raise ViewError("role does not match request")
    source = _source_report(sources, req)
    intents = _links(intent_links, req, "intent")
    acceptances = _links(acceptance_links, req, "acceptance")
    dependencies = _links(dependency_freshness, req, "dependency")
    if len(acceptances) > 1:
        raise ViewError("duplicate current acceptance link")
    entries = source["sources"]
    by_kind = {item["kind"]: item for item in entries}
    task_entry = by_kind.get("kit:TASKS.md")
    notes_entry = by_kind.get("kit:NOTES.md")
    event_entry = by_kind.get("attempt-events")
    task = None
    if task_entry and task_entry["state"] == "ok":
        matches = [item for item in task_entry["observed"]
                   if item.get("id") == req["task_id"]]
        if len(matches) == 1:
            task = matches[0]

    findings, relationships, limitations = [], [], []
    output_redactions = {}

    def finding(kind, claim, epistemic, basis, *, applicability="subject-matched", critical=False):
        if len(findings) >= MAX_FINDINGS:
            raise ViewError("too many findings")
        item = {"id": "f" + str(len(findings) + 1), "kind": kind,
                "claim": _text(claim, output_redactions), "epistemic": epistemic,
                "applicability": applicability, "basis": basis, "critical": bool(critical)}
        findings.append(item)
        return item["id"]

    def limitation(code, detail, basis, *, critical=True):
        item = {"code": code, "detail": _text(detail, output_redactions), "critical": bool(critical),
                "basis": basis}
        limitations.append(item)
        return item

    task_basis = _basis(task_entry["ref"], "TASKS.md task " + req["task_id"]) \
        if task_entry and task_entry["state"] == "ok" else _basis(missing="tasks-unavailable")
    if task is None:
        limitation("task-unavailable", "Selected task and its criteria are unavailable", [task_basis])
    else:
        finding("task-status", "task status: " + str(task["status"]), "recorded",
                [task_basis])
        if not task.get("acceptance"):
            limitation("criteria-missing", "Mandatory acceptance criteria are missing", [task_basis])
        for dep in task.get("depends") or []:
            relationships.append({"kind": "declared-dependency", "from": req["task_id"],
                                  "to": dep, "epistemic": "recorded", "basis": [task_basis]})
        for graph_finding in _kit.validate_graph(task_entry["observed"]):
            finding("task-graph", graph_finding["kind"], "recorded", [task_basis], critical=True)
            limitation("task-graph-invalid", "Task graph has a structural finding", [task_basis])

    graph_entry = by_kind.get("graph")
    if graph_entry and graph_entry["state"] == "ok":
        graph_basis = [_basis(graph_entry["ref"], "graph links")]
        graph_data = graph_entry["observed"]
        for edge in graph_data.get("links") or []:
            relationships.append({"kind": "code-navigation", "from": str(edge.get("source")),
                                  "to": str(edge.get("target")), "epistemic": "recorded",
                                  "basis": graph_basis})

    for item in entries:
        if item["state"] != "ok" or not item["coverage"].get("complete", False):
            limitation("source-" + item["kind"].replace(":", "-") + "-" + item["state"],
                       "Selected source coverage is incomplete", [_basis(item["ref"], item["kind"],
                                                                           "source-unavailable")],
                       critical=item["kind"] == "kit:TASKS.md")

    if req["source_state_ref"] is not None:
        limitation("source-state-unverified", "Declared source state is not attested by CT2",
                   [_basis(req["source_state_ref"], "request.source_state_ref")], critical=False)
    if req["source_ref"] is not None:
        pin = req["source_ref"]
        comparable = [item["ref"] for item in entries if item["ref"] is not None
                      and item["ref"]["id"] == pin["id"] and item["ref"]["v"] == pin["v"]]
        if not comparable or pin["sha"] is None or any(ref["sha"] is None for ref in comparable):
            limitation("source-pin-unknown", "Selected source pin cannot be compared",
                       [_basis(pin, "request.source_ref")])
        elif all(ref["sha"] != pin["sha"] for ref in comparable):
            limitation("source-pin-mismatch", "Comparable source bytes differ from the request pin",
                       [_basis(pin, "request.source_ref")])

    if acceptances:
        current = acceptances[0]["ref"]
        prior = req["acceptance_ref"]
        finding("acceptance-link", "Current acceptance reference was declared by caller",
                "caller-declared", [_basis(current, "acceptance_links[0].ref")],
                applicability="caller-declared")
        if prior is not None and current != prior:
            limitation("acceptance-ref-mismatch", "Declared current acceptance differs from request pin",
                       [_basis(prior, "request.acceptance_ref"), _basis(current, "acceptance_links[0].ref")])
    elif req["acceptance_ref"] is not None:
        limitation("acceptance-current-unknown", "Current acceptance reference is not supplied",
                   [_basis(req["acceptance_ref"], "request.acceptance_ref")], critical=False)

    for item in intents:
        finding("intent-link", "Caller declared an intent link: " + item["kind"],
                "caller-declared", [_basis(item["ref"], "intent_links.ref")],
                applicability="caller-declared")

    deps_by_id = {item["subject"]["task_id"]: item for item in dependencies}
    if task is not None:
        actual_deps = set(task.get("depends") or [])
        if any(dep not in actual_deps for dep in deps_by_id):
            raise ViewError("dependency link not declared by task")
        for dep in task.get("depends") or []:
            item = deps_by_id.get(dep)
            if item is None:
                if task["status"] == "done":
                    limitation("dependency-freshness-unknown", "Dependency freshness is not supplied",
                               [task_basis])
                continue
            basis = [_basis(item["ref"], "dependency_freshness.ref", "dependency-ref-unknown")]
            finding("dependency-freshness", "Dependency freshness declared: " + item["state"],
                    "caller-declared", basis, applicability="caller-declared",
                    critical=item["state"] == "stale")
            if item["state"] == "stale":
                limitation("dependency-stale-declared", "Dependency was declared stale", basis)
            elif item["state"] == "unknown" and task["status"] == "done":
                limitation("dependency-freshness-unknown", "Dependency freshness is unknown", basis)

    notes_result = None
    if task is not None and notes_entry and notes_entry["state"] == "ok":
        notes_result = _kit.recorded_outcome_result(notes_entry["observed"]["text"], req["task_id"])
        if notes_result is not None:
            basis = [_basis(notes_entry["ref"], "NOTES.md outcome for " + req["task_id"])]
            finding("recorded-outcome", "NOTES result: " + notes_result, "recorded", basis)
            relationships.append({"kind": "recorded-outcome", "from": req["task_id"],
                                  "to": notes_result, "epistemic": "recorded", "basis": basis})
            if (task["status"] == "done" and notes_result == "blocked") \
                    or (task["status"] != "done" and notes_result in _kit._PASS_RESULTS):
                limitation("status-outcome-conflict", "Task status conflicts with NOTES outcome",
                           [task_basis] + basis)
            elif notes_result not in _kit._PASS_RESULTS + ("blocked", "budget-stop"):
                limitation("outcome-result-unknown", "Recorded outcome label has no known verdict semantics",
                           basis, critical=False)

    prior_prechecks = {}
    meaningful_precheck = False
    tautological_precheck = False
    pass_claim = bool(task and task["status"] == "done") or notes_result in _kit._PASS_RESULTS
    if event_entry and event_entry["state"] == "ok":
        for event in event_entry["observed"]:
            if event.get("task") != req["task_id"]:
                continue
            ev_kind = event.get("kind")
            ev_basis = [_basis(event_entry["ref"], "attempt event " + str(ev_kind))]
            intrinsic = (event.get("repository_id") == req["repository_id"]
                         and event.get("kit_path") == req["kit_path"])
            named_elsewhere = (event.get("repository_id") is not None
                               or event.get("kit_path") is not None)
            applicability = ("subject-matched" if intrinsic else
                             "mismatch" if named_elsewhere else "unbound")
            finding("attempt-event", "Ledger event recorded: " + str(ev_kind), "recorded",
                    ev_basis, applicability=applicability)
            acceptance_aligned = (req["acceptance_ref"] is None or
                                  event.get("acceptance_ref") == req["acceptance_ref"])
            if ev_kind == "verify.precheck" and intrinsic and acceptance_aligned and event.get("run"):
                prior_prechecks.setdefault(event["run"], []).append(event)
            if intrinsic and ev_kind == "verify.finished" and event.get("rc") == 0:
                pass_claim = True
                if event.get("run") and acceptance_aligned:
                    earlier = prior_prechecks.get(event["run"], [])
                    meaningful_precheck |= any(pre.get("tautological") is False and
                                               type(pre.get("rc")) is int and pre["rc"] != 0
                                               for pre in earlier)
                    tautological_precheck |= any(pre.get("tautological") is True for pre in earlier)
                relationships.append({"kind": "measured-verification", "from": req["task_id"],
                                      "to": "rc=0", "epistemic": "recorded", "basis": ev_basis})
            if intrinsic and ev_kind == "task.projected" and event.get("status") == "done":
                pass_claim = True
                if task and task["status"] != "done":
                    limitation("status-ledger-conflict", "Task status conflicts with a ledger projection",
                               [task_basis] + ev_basis)
            if intrinsic and req["acceptance_ref"] is not None:
                ev_ref = event.get("acceptance_ref")
                if ev_ref is not None and ev_ref != req["acceptance_ref"]:
                    limitation("event-acceptance-mismatch", "Event acceptance reference differs from request",
                               [ev_basis, _basis(req["acceptance_ref"], "request.acceptance_ref")])
    if pass_claim and (not meaningful_precheck or tautological_precheck):
        limitation("precheck-unproven" if not tautological_precheck else "precheck-tautological",
                   "A meaningful precheck is not established for the recorded pass claim",
                   [_basis(event_entry["ref"], "attempt-events", "precheck-missing")]
                   if event_entry else [_basis(missing="precheck-missing")])
    elif pass_claim:
        limitation("precheck-semantic-adequacy-unknown",
                   "A prior failing precheck was recorded for the same run; its command and independent adequacy are unknown",
                   [_basis(event_entry["ref"], "attempt-events")], critical=False)

    task_status = task["status"] if task else None
    title = _text(task["title"], output_redactions) if task else None
    criteria_text = _text(task["acceptance"], output_redactions) if task else None
    source_states = [{key: copy.deepcopy(item[key]) for key in
                      ("kind", "state", "ref", "consistency", "freshness", "redactions")}
                     for item in entries]
    overview = {"task_status": task_status, "task_title": title,
                "source_states": source_states,
                "coverage_complete": bool(source["coverage"]["complete"]),
                "redactions": output_redactions}
    critical = [item for item in limitations if item["critical"]]
    focus_order = {
        "architect": ("task-graph", "intent-link", "task-status", "dependency-freshness"),
        "implementer": ("task-status", "dependency-freshness", "task-graph", "intent-link"),
        "verifier": ("attempt-event", "recorded-outcome", "task-status", "dependency-freshness"),
        "reviewer": ("recorded-outcome", "attempt-event", "task-graph", "task-status"),
    }[role]
    rank = {kind: i for i, kind in enumerate(focus_order)}
    focus = [item["id"] for item in sorted(findings,
              key=lambda item: (rank.get(item["kind"], len(rank)), int(item["id"][1:])))]
    brief = {"role": role, "summary": title,
             "criteria_text": criteria_text,
             "focus": focus, "critical_limitations": copy.deepcopy(critical)}
    status = "partial" if critical else "complete"
    view = {"v": CONTRACT_VERSION, "kind": "projection", "status": status,
            "request": copy.deepcopy(req), "subject": _subject(req), "overview": overview,
            "brief": brief, "findings": findings, "relationships": relationships,
            "limitations": limitations}
    try:
        view["content_sha"] = _view_digest(view)
        _validate_view(view)
        if len(canonical_bytes(view)) <= max_bytes:
            return view
    except ViewError as exc:
        if str(exc) != "payload exceeds limit":
            raise
    refused = {"v": CONTRACT_VERSION, "kind": "projection", "status": "refused",
               "request": copy.deepcopy(req), "subject": _subject(req),
               "overview": {"task_status": task_status, "task_title": title,
                            "source_states": [], "coverage_complete": False,
                            "redactions": output_redactions},
               "brief": None, "findings": [], "relationships": [],
               "limitations": [{"code": "budget", "detail": "View exceeds output budget",
                                "critical": True, "basis": [_basis(missing="output-budget")]}]}
    refused["content_sha"] = _view_digest(refused)
    if len(canonical_bytes(refused)) > max_bytes:
        raise ViewError("view exceeds budget")
    return _validate_view(refused)


def compare_views(before, after, *, max_bytes=MAX_BYTES):
    """Compare two validated projections, separating applicability from facts."""
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES:
        raise ViewError("invalid output budget")
    left = _validate_view(copy.deepcopy(before))
    right = _validate_view(copy.deepcopy(after))
    if left["kind"] != "projection" or right["kind"] != "projection":
        raise ViewError("comparison needs projections")
    stable = ("repository_id", "kit_path", "task_identity")
    if any(left["subject"][key] != right["subject"][key] for key in stable):
        raise ViewError("stable subject mismatch")
    applicability = []
    for key in ("checkout_id", "revision", "source_state_ref"):
        if left["subject"][key] != right["subject"][key]:
            applicability.append({"field": key, "before": left["subject"][key],
                                  "after": right["subject"][key]})
    changes = []
    for field, before_value, after_value in (
        ("view-status", left["status"], right["status"]),
        ("task-status", left["overview"]["task_status"], right["overview"]["task_status"]),
        ("criteria-text", (left["brief"] or {}).get("criteria_text"),
         (right["brief"] or {}).get("criteria_text")),
        ("acceptance-ref", left["request"]["acceptance_ref"], right["request"]["acceptance_ref"]),
        ("source-states", left["overview"]["source_states"], right["overview"]["source_states"]),
        ("findings", left["findings"], right["findings"]),
        ("limitations", left["limitations"], right["limitations"]),
    ):
        if before_value != after_value:
            changes.append({"field": field, "before": before_value, "after": after_value,
                            "epistemic": "observed-change-not-proof"})
    subject = {key: copy.deepcopy(left["subject"][key]) for key in stable}
    out = {"v": CONTRACT_VERSION, "kind": "comparison", "subject": subject,
           "before_sha": left["content_sha"], "after_sha": right["content_sha"],
           "applicability_changes": applicability, "changes": changes,
           "limitations": [{"code": "comparison-is-not-proof",
                            "detail": "Changed observations do not prove requirements were removed or met",
                            "critical": False, "basis": [_basis(missing="comparison-only")]}]}
    out["content_sha"] = _view_digest(out)
    if len(canonical_bytes(out)) > max_bytes:
        raise ViewError("comparison exceeds budget")
    return _validate_view(out)
