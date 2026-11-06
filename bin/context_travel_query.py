"""CT4: bounded, read-only queries over explicit startup bindings."""

import copy
import importlib.util
import json
import math
from pathlib import Path


CONFIG_VERSION = "polytropos.context-query-config/1"
QUERY_VERSION = "polytropos.context-query/1"
OPERATIONS = ("overview", "brief", "explain", "changes", "capabilities")
MAX_CONFIG_BYTES = 16384
MAX_OUTPUT_BYTES = 32768
MAX_INPUT_BYTES = 131072
MAX_BINDINGS = 32


class QueryError(ValueError):
    """Invalid, unauthorized, or unrepresentable query."""


def _sibling(name):
    path = Path(__file__).resolve().with_name(name + ".py")
    spec = importlib.util.spec_from_file_location("context_travel_query_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_ct = _sibling("context_travel")
_readers = _sibling("context_readers")
_view = _sibling("lifecycle_view")
_safe = _sibling("safe_paths")
_redact = _sibling("redact")


def _walk(value, depth=0):
    if depth > 20:
        raise QueryError("JSON nesting exceeds limit")
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if math.isfinite(value):
            return
        raise QueryError("nonfinite number")
    if type(value) is list:
        if len(value) > 256:
            raise QueryError("JSON collection exceeds limit")
        for item in value:
            _walk(item, depth + 1)
        return
    if type(value) is dict:
        if len(value) > 256 or any(type(key) is not str for key in value):
            raise QueryError("invalid JSON object")
        for item in value.values():
            _walk(item, depth + 1)
        return
    raise QueryError("non-JSON value")


def _encode(value, ceiling):
    _walk(value)
    try:
        data = json.dumps(value, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise QueryError("invalid JSON value") from None
    if len(data) > ceiling:
        raise QueryError("JSON payload exceeds limit")
    return data


def canonical_bytes(envelope):
    """Canonical bounded UTF-8 encoding of a query result."""
    if type(envelope) is not dict or set(envelope) != {"v", "operation", "data"} \
            or envelope["v"] != QUERY_VERSION or envelope["operation"] not in OPERATIONS:
        raise QueryError("invalid query envelope")
    return _encode(envelope, MAX_OUTPUT_BYTES)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise QueryError("duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(_value):
    raise QueryError("nonfinite JSON number")


def parse_json(raw, *, max_bytes=MAX_INPUT_BYTES):
    """Parse a bounded JSON frame with duplicate-key and depth rejection."""
    if type(raw) not in (bytes, str):
        raise QueryError("JSON input must be bytes or text")
    try:
        data = raw.encode("utf-8") if type(raw) is str else raw
        if len(data) > max_bytes:
            raise QueryError("JSON payload exceeds limit")
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=_nonfinite)
        _walk(value)
        _encode(value, max_bytes)
        return value
    except (UnicodeError, ValueError, RecursionError):
        raise QueryError("invalid JSON input") from None


def _keys(value, expected):
    if type(value) is not dict or set(value) != set(expected):
        raise QueryError("unexpected or missing fields")


def _relative(value):
    if (type(value) is not str or len(value) > _ct.MAX_ID or "\\" in value
            or ":" in value or _redact.scan(value)
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise QueryError("invalid selected path") from None
    try:
        parts = _safe.safe_parts(value, what="selected source")
    except _safe.SafePathError:
        raise QueryError("invalid selected path") from None
    if "/".join(parts) != value:
        raise QueryError("invalid selected path")
    return value


def _root(value):
    if (type(value) is not str or len(value) > 1024 or _redact.scan(value)
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise QueryError("invalid root binding")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or str(path) != value:
        raise QueryError("invalid root binding")
    return value


def _config(value):
    _encode(value, MAX_CONFIG_BYTES)
    _keys(value, ("v", "repositories", "deny_prefixes", "limits", "max_output_bytes"))
    if value["v"] != CONFIG_VERSION:
        raise QueryError("unsupported config version")
    if type(value["max_output_bytes"]) is not int or not 1024 <= value["max_output_bytes"] <= MAX_OUTPUT_BYTES:
        raise QueryError("invalid output bound")
    try:
        limits = _readers._limits(value["limits"])
    except (ValueError, TypeError):
        raise QueryError("invalid source policy") from None
    raw_denials = value["deny_prefixes"]
    if type(raw_denials) is not list or len(raw_denials) > 64:
        raise QueryError("invalid source policy")
    denials = []
    for prefix in raw_denials:
        if type(prefix) is not str or prefix.endswith("//"):
            raise QueryError("invalid source policy")
        denials.append(_relative(prefix[:-1] if prefix.endswith("/") else prefix))
    repositories = value["repositories"]
    if type(repositories) is not list or not 1 <= len(repositories) <= MAX_BINDINGS:
        raise QueryError("invalid repository bindings")
    seen_repos, seen_evidence, total_kits = set(), set(), 0
    clean = []
    for repository in repositories:
        _keys(repository, ("id", "root", "kits"))
        try:
            repo_id = _ct._identifier(repository["id"], "repository ID")
        except ValueError:
            raise QueryError("invalid repository identity") from None
        if repo_id in seen_repos:
            raise QueryError("duplicate repository binding")
        seen_repos.add(repo_id)
        repo_root = _root(repository["root"])
        kits = repository["kits"]
        if type(kits) is not list or not 1 <= len(kits) <= MAX_BINDINGS:
            raise QueryError("invalid kit bindings")
        seen_kits, clean_kits = set(), []
        for kit in kits:
            total_kits += 1
            if total_kits > MAX_BINDINGS:
                raise QueryError("too many kit bindings")
            _keys(kit, ("path", "kit_files", "graph_path", "evidence"))
            kit_path = _relative(kit["path"])
            parts = kit_path.split("/")
            if not (len(parts) == 3 and parts[:2] in ([".claude", "kits"], ["tasks", "kits"])):
                raise QueryError("invalid kit binding")
            if kit_path in seen_kits or _redact.scan(parts[2]):
                raise QueryError("duplicate or invalid kit binding")
            seen_kits.add(kit_path)
            files = kit["kit_files"]
            if (type(files) is not list or len(files) > len(_readers.KIT_FILES)
                    or any(type(name) is not str for name in files)
                    or len(set(files)) != len(files)
                    or any(name not in _readers.KIT_FILES for name in files)):
                raise QueryError("invalid selected kit files")
            graph = None if kit["graph_path"] is None else _relative(kit["graph_path"])
            evidence = kit["evidence"]
            if evidence is not None:
                _keys(evidence, ("root", "events_rel"))
                evidence = {"root": _root(evidence["root"]),
                            "events_rel": _relative(evidence["events_rel"])}
                key = (evidence["root"], evidence["events_rel"])
                if key in seen_evidence:
                    raise QueryError("ambiguous evidence binding")
                seen_evidence.add(key)
            clean_kits.append({"path": kit_path, "kit_files": list(files),
                               "graph_path": graph, "evidence": evidence})
        clean.append({"id": repo_id, "root": repo_root, "kits": clean_kits})
    return {"v": CONFIG_VERSION, "repositories": clean,
            "deny_prefixes": list(denials), "limits": limits,
            "max_output_bytes": value["max_output_bytes"]}


def parse_config(raw):
    """Validate a complete, closed startup configuration supplied in memory."""
    return _config(parse_json(raw, max_bytes=MAX_CONFIG_BYTES))


def load_config(config_path):
    """Read only one explicit absolute config file through the stable confined reader."""
    if (type(config_path) is not str or len(config_path) > 2048
            or any(ord(char) < 32 or ord(char) == 127 for char in config_path)):
        raise QueryError("invalid config path")
    path = Path(config_path)
    if (not path.is_absolute() or ".." in path.parts or str(path) != config_path
            or path.name in ("", ".", "..")):
        raise QueryError("invalid config path")
    try:
        result = _safe.confined_read_stable_bytes(path.parent, path.name,
                                                   max_bytes=MAX_CONFIG_BYTES,
                                                   read_budget=2 * MAX_CONFIG_BYTES)
        return parse_config(result["data"])
    except (ValueError, OSError, TypeError):
        raise QueryError("startup config unavailable or invalid") from None


def _bound(config, subject):
    if type(subject) is not dict:
        raise QueryError("invalid subject")
    repo_id, kit_path = subject.get("repository_id"), subject.get("kit_path")
    for repository in config["repositories"]:
        if repository["id"] == repo_id:
            for kit in repository["kits"]:
                if kit["path"] == kit_path:
                    return repository, kit
    raise QueryError("subject is not configured")


def _projection(value, config):
    try:
        parsed = _view.parse_view(_view.canonical_bytes(value))
    except (ValueError, TypeError, RecursionError):
        raise QueryError("invalid lifecycle artifact") from None
    if parsed["kind"] != "projection":
        raise QueryError("projection required")
    _bound(config, parsed["subject"])
    return parsed


def _request(value, config, args):
    try:
        request = _ct.parse_request(_ct.canonical_bytes(value))
        if request["assignment_role"] not in _view.ROLES:
            raise QueryError("unsupported assignment role")
        _view._links(args.get("intent_links", []), request, "intent")
        _view._links(args.get("acceptance_links", []), request, "acceptance")
        _view._links(args.get("dependency_freshness", []), request, "dependency")
    except (ValueError, TypeError, RecursionError):
        raise QueryError("invalid query request") from None
    repository, kit = _bound(config, request)
    return request, repository, kit


def _assignment(value):
    required = ("repository_id", "checkout_id", "revision", "kit_path", "task_id",
                "assignment_id", "assignment_role", "question")
    optional = ("source_state_ref", "source_ref", "acceptance_ref")
    if type(value) is not dict or not set(required) <= set(value) \
            or not set(value) <= set(required + optional):
        raise QueryError("invalid assignment")
    if type(value["question"]) is not str:
        raise QueryError("invalid assignment question")
    try:
        return _ct.make_request(*(value[name] for name in required),
                                **{name: value.get(name) for name in optional})
    except (ValueError, TypeError, RecursionError):
        raise QueryError("invalid assignment") from None


def _arguments(operation, args):
    if type(args) is not dict:
        raise QueryError("arguments must be an object")
    if operation in ("overview", "brief"):
        if set(args) == {"view"}:
            return "imported"
        allowed = {"request", "intent_links", "acceptance_links", "dependency_freshness"}
        if "request" in args and set(args) <= allowed:
            return "live"
        allowed = {"assignment", "intent_links", "acceptance_links", "dependency_freshness"}
        if "assignment" in args and set(args) <= allowed:
            return "assignment"
    elif operation == "explain" and set(args) == {"view", "finding_id"}:
        return "explain"
    elif operation == "changes" and set(args) == {"before", "after"}:
        return "changes"
    elif operation == "capabilities" and not args:
        return "capabilities"
    raise QueryError("invalid query arguments")


def _envelope(config, operation, data):
    out = {"v": QUERY_VERSION, "operation": operation, "data": data}
    if len(canonical_bytes(out)) > config["max_output_bytes"]:
        raise QueryError("query exceeds output bound")
    return out


def run_query(config, operation, args):
    """Execute one bounded operation; only live projection forms read selected sources."""
    if type(operation) is not str or operation not in OPERATIONS:
        raise QueryError("unknown query operation")
    # Accept a parsed config, but revalidate it to keep direct API callers honest.
    try:
        policy = _config(config)
    except (ValueError, TypeError, RecursionError):
        raise QueryError("invalid query config") from None
    _walk(args)
    _encode(args, MAX_INPUT_BYTES)
    form = _arguments(operation, args)
    if form == "capabilities":
        data = {"operations": list(OPERATIONS),
                "contracts": [_ct.CONTRACT_VERSION, _readers.CONTRACT_VERSION,
                              _view.CONTRACT_VERSION, QUERY_VERSION],
                "max_output_bytes": policy["max_output_bytes"],
                "client_support": "unverified",
                "historical_storage": "none"}
    elif form in ("live", "assignment"):
        source_request = args["request"] if form == "live" else _assignment(args["assignment"])
        request, repository, kit = _request(source_request, policy, args)
        if len(args.get("acceptance_links", [])) > 1:
            raise QueryError("duplicate acceptance declaration")
        evidence = ({(repository["id"], kit["path"]): kit["evidence"]}
                    if kit["evidence"] is not None else None)
        try:
            observed = _readers.read_sources(
                repository_bindings={repository["id"]: repository["root"]},
                repository_id=repository["id"], kit_path=kit["path"],
                kit_files=tuple(kit["kit_files"]), graph_path=kit["graph_path"],
                evidence_bindings=evidence, deny_prefixes=tuple(policy["deny_prefixes"]),
                limits=policy["limits"])
            data = _view.compose_view(request, observed,
                role=request["assignment_role"],
                intent_links=args.get("intent_links", []),
                acceptance_links=args.get("acceptance_links", []),
                dependency_freshness=args.get("dependency_freshness", []),
                max_bytes=min(_view.MAX_BYTES, policy["max_output_bytes"]))
        except (ValueError, TypeError, OSError, RecursionError):
            raise QueryError("query could not form a bounded view") from None
    elif form == "imported":
        data = _projection(args["view"], policy)
    elif form == "explain":
        view = _projection(args["view"], policy)
        fid = args["finding_id"]
        if fid is not None and (type(fid) is not str or not fid or len(fid) > 32):
            raise QueryError("invalid finding selector")
        findings = [item for item in view["findings"] if fid is None or item["id"] == fid]
        if fid is not None and not findings:
            raise QueryError("finding not present")
        data = {"subject": copy.deepcopy(view["subject"]),
                "view_sha": view["content_sha"], "findings": copy.deepcopy(findings),
                "critical_limitations": [copy.deepcopy(item) for item in view["limitations"]
                                         if item["critical"]],
                "criteria_text": (view["brief"] or {}).get("criteria_text"),
                "source_states": copy.deepcopy(view["overview"]["source_states"]),
                "coverage_complete": view["overview"]["coverage_complete"]}
    else:
        before = _projection(args["before"], policy)
        after = _projection(args["after"], policy)
        try:
            data = _view.compare_views(before, after,
                                       max_bytes=min(_view.MAX_BYTES,
                                                     policy["max_output_bytes"]))
        except (ValueError, TypeError, RecursionError):
            raise QueryError("views cannot be compared") from None
    return _envelope(policy, operation, data)


def render_text(envelope, *, max_bytes):
    """Readable, complete JSON text. Refuse if it cannot fit without omission."""
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_OUTPUT_BYTES:
        raise QueryError("invalid text bound")
    canonical_bytes(envelope)
    text = json.dumps(envelope, ensure_ascii=False, sort_keys=True, indent=2)
    if len(text.encode("utf-8")) > max_bytes:
        raise QueryError("text exceeds output bound")
    return text
