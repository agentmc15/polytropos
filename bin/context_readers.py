"""CT2: selected, bounded, privacy-aware source observations; no execution authority."""

import hashlib
import importlib.util
import json
import math
from pathlib import Path


CONTRACT_VERSION = "polytropos.context-sources/1"
KIT_FILES = ("PLAN.md", "TASKS.md", "GUARDRAILS.md", "NOTES.md")
DEFAULT_LIMITS = {"max_sources": 8, "max_source_bytes": 65536,
                  "max_total_bytes": 262144, "max_items": 64}
LIMIT_CEILINGS = {"max_sources": 16, "max_source_bytes": 262144,
                  "max_total_bytes": 1048576, "max_items": 256}


class SourceLimitError(ValueError):
    """Selected facts cannot fit the declared observation bound."""

_SIBLINGS = {}


def _sibling(name):
    if name not in _SIBLINGS:
        path = Path(__file__).resolve().with_name(name + ".py")
        spec = importlib.util.spec_from_file_location("context_readers_" + name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SIBLINGS[name] = module
    return _SIBLINGS[name]


def _limits(value):
    result = dict(DEFAULT_LIMITS) if value is None else value
    if type(result) is not dict or set(result) != set(DEFAULT_LIMITS):
        raise ValueError("invalid source limits")
    for name, ceiling in LIMIT_CEILINGS.items():
        if type(result[name]) is not int or not 1 <= result[name] <= ceiling:
            raise ValueError("invalid source limit")
    return dict(result)


def _relative(value):
    sp = _sibling("safe_paths")
    ct = _sibling("context_travel")
    if type(value) is not str or len(value) > ct.MAX_ID or "\\" in value or ":" in value:
        raise ValueError("invalid relative path")
    try:
        parts = sp.safe_parts(value, what="selected source")
    except sp.SafePathError:
        raise ValueError("invalid relative path") from None
    if "/".join(parts) != value or _sibling("redact").scan(value):
        raise ValueError("invalid relative path")
    return value


def _root(value):
    try:
        path = Path(value)
    except TypeError:
        raise ValueError("invalid root binding") from None
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("repository or evidence root must be absolute")
    return path


def _denials(values):
    if type(values) not in (list, tuple) or len(values) > 64:
        raise ValueError("invalid deny rules")
    cleaned = []
    for value in values:
        if type(value) is not str or value.endswith("//"):
            raise ValueError("invalid deny rule")
        cleaned.append(_relative(value[:-1] if value.endswith("/") else value))
    return tuple(cleaned)


def _denied(rel, prefixes):
    return any(rel == prefix or rel.startswith(prefix + "/") for prefix in prefixes)


def _eligible(rel, prefixes, *, structural_kit=False):
    if _denied(rel, prefixes):
        return False
    # The selected native kit directory is a structural dot path, not a hidden
    # source discovered by search. Its filename still passes the privacy rules.
    if structural_kit and rel.startswith(".claude/kits/"):
        return _sibling("decision_context").privacy_rule(rel.rsplit("/", 1)[-1]) is None
    return _sibling("decision_context").privacy_rule(rel, prefixes) is None


def _counts_add(into, found):
    for kind, count in found.items():
        into[kind] = into.get(kind, 0) + count


def _clean(value, counts, max_items, *, field=None, depth=0):
    if depth > 12:
        raise ValueError("source nesting exceeds limit")
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("nonfinite source number")
        return value
    if type(value) is str:
        redact = _sibling("redact")
        if field in ("id", "task", "run", "attempt", "source", "target", "kind",
                     "sha", "v", "artifact", "model", "requested_model",
                     "dispatched_model", "observed_model", "role", "phase",
                     "status", "result", "op"):
            if redact.scan(value):
                raise ValueError("credential-shaped source identifier")
            return value
        result = redact.redact(value, limit=None)
        _counts_add(counts, result["redactions"])
        return result["text"]
    if type(value) is list:
        if len(value) > max_items:
            raise SourceLimitError("source item limit")
        return [_clean(item, counts, max_items, depth=depth + 1) for item in value]
    if type(value) is dict:
        if len(value) > max_items or any(type(k) is not str for k in value):
            raise SourceLimitError("source item limit")
        if any(_sibling("redact").scan(k) for k in value):
            raise ValueError("credential-shaped source key")
        return {k: _clean(v, counts, max_items, field=k, depth=depth + 1)
                for k, v in value.items()}
    raise ValueError("invalid source value")


def _observation(kind, state="absent", *, ref=None, observed=None, consistency="unknown",
                 items=0, retained_bytes=0, redactions=None, exclusions=None, reason_code=None):
    exclusions = exclusions or {}
    return {"kind": kind, "state": state, "ref": ref, "observed": observed,
            "freshness": {"state": "unknown", "basis": "not-assessed"},
            "consistency": consistency,
            "coverage": {"complete": state == "ok" and not exclusions, "items": items,
                         "retained_bytes": retained_bytes},
            "redactions": redactions or {}, "exclusions": exclusions,
            "reason_code": reason_code}


def _source_ref(repo_id, kit_path, kind, rel, raw, version):
    material = json.dumps([repo_id, kit_path, kind, rel], ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8")
    identity = hashlib.sha256(material).hexdigest()[:32]
    return _sibling("attempt_ledger").make_ref("source:" + identity,
                                                sha=hashlib.sha256(raw).hexdigest(),
                                                version=version)


def _selected_observed(kind, raw, max_items, deny_prefixes):
    counts = {}
    if kind == "kit:TASKS.md":
        tasks = _sibling("kit_contract").parse_tasks(raw.decode("utf-8"))
        if len(tasks) > max_items:
            raise SourceLimitError("task item limit")
        for task in tasks:
            for identity in [task["id"]] + list(task.get("depends") or []):
                if _sibling("redact").scan(identity):
                    raise ValueError("credential-shaped task identity")
        return _clean(tasks, counts, max_items), len(tasks), counts, {}
    if kind.startswith("kit:"):
        return {"text": _clean(raw.decode("utf-8"), counts, max_items)}, 1, counts, {}
    if kind == "graph":
        graph, error = _sibling("graph_brief").parse_graph_bytes(raw, strict=True,
                                                                   max_items=max_items)
        if error:
            if "item limit" in error:
                raise SourceLimitError("graph item limit")
            raise ValueError("invalid graph")
        nodes = _sibling("graph_brief")._nodes_of(graph)
        links = _sibling("graph_brief")._links_of(graph)
        if len(nodes) + len(links) > max_items:
            raise SourceLimitError("graph item limit")
        selected, allowed, excluded = [], set(), {}
        for node in nodes:
            if type(node) is not dict:
                raise ValueError("invalid graph node")
            rel = node.get("source_file")
            if rel is not None:
                try:
                    _relative(rel)
                except ValueError:
                    excluded["invalid-path"] = excluded.get("invalid-path", 0) + 1
                    continue
                rule = _sibling("decision_context").privacy_rule(rel, deny_prefixes)
                if rule is not None:
                    excluded[rule] = excluded.get(rule, 0) + 1
                    continue
            entry = {k: node.get(k) for k in ("id", "label", "name", "source_file")
                     if k in node}
            selected.append(_clean(entry, counts, max_items))
            allowed.add(node.get("id"))
        edges = []
        for link in links:
            if type(link) is not dict:
                raise ValueError("invalid graph edge")
            if link.get("source") in allowed and link.get("target") in allowed:
                edges.append(_clean({k: link.get(k) for k in ("source", "target", "relation")
                                     if k in link}, counts, max_items))
            else:
                excluded["withheld-edge"] = excluded.get("withheld-edge", 0) + 1
        return {"nodes": selected, "links": edges}, len(selected) + len(edges), counts, excluded
    events, corrupt = _sibling("attempt_ledger").parse_events(raw, strict=True,
                                                                max_items=max_items)
    if corrupt or len(events) > max_items:
        if len(events) > max_items:
            raise SourceLimitError("event item limit")
        raise ValueError("invalid attempt events")
    for event in events:
        event["provenance"] = _sibling("attempt_ledger").provenance(event)
    return _clean(events, counts, max_items), len(events), counts, {}


def read_sources(*, repository_bindings, repository_id, kit_path, kit_files=("TASKS.md",),
                 graph_path=None, evidence_bindings=None, deny_prefixes=(), limits=None):
    """Observe exactly selected sources under explicit bindings and physical read caps."""
    cfg = _limits(limits)
    ct = _sibling("context_travel")
    ct._identifier(repository_id, "repository ID")
    if (type(repository_bindings) is not dict or len(repository_bindings) > 32
            or repository_id not in repository_bindings):
        raise ValueError("repository is not bound")
    for bound_id, bound_root in repository_bindings.items():
        ct._identifier(bound_id, "repository ID")
        _root(bound_root)
    repo_root = _root(repository_bindings[repository_id])
    _relative(kit_path)
    parts = kit_path.split("/")
    if not (len(parts) == 3 and (parts[:2] == [".claude", "kits"]
                                or parts[:2] == ["tasks", "kits"])):
        raise ValueError("unsupported kit path")
    if _sibling("decision_context").privacy_rule(parts[2]) is not None:
        raise ValueError("invalid kit identity")
    if type(kit_files) not in (list, tuple) or len(kit_files) > len(KIT_FILES) \
            or any(type(name) is not str for name in kit_files) \
            or len(set(kit_files)) != len(kit_files) or any(name not in KIT_FILES for name in kit_files):
        raise ValueError("invalid kit selection")
    if graph_path is not None:
        _relative(graph_path)
    denied = _denials(deny_prefixes)
    if evidence_bindings is not None and (type(evidence_bindings) is not dict
                                           or len(evidence_bindings) > 32):
        raise ValueError("invalid evidence bindings")
    for key, item in (evidence_bindings or {}).items():
        if (type(key) is not tuple or len(key) != 2 or type(item) is not dict
                or set(item) != {"root", "events_rel"}):
            raise ValueError("invalid evidence binding")
        ct._identifier(key[0], "repository ID")
        _relative(key[1])
        _root(item["root"])
        _relative(item["events_rel"])

    selection = [("kit:" + name, repo_root, kit_path + "/" + name, True, None)
                 for name in kit_files]
    if graph_path is not None:
        selection.append(("graph", repo_root, graph_path, False, None))
    binding = (evidence_bindings or {}).get((repository_id, kit_path))
    if binding is not None:
        if type(binding) is not dict or set(binding) != {"root", "events_rel"}:
            raise ValueError("invalid evidence binding")
        evidence_root = _root(binding["root"])
        events_rel = _relative(binding["events_rel"])
        selected_name = str(evidence_root / events_rel)
        ambiguous = any(key != (repository_id, kit_path) and
                        type(other) is dict and "root" in other and "events_rel" in other and
                        str(_root(other["root"]) / _relative(other["events_rel"])) == selected_name
                        for key, other in evidence_bindings.items())
        selection.append(("attempt-events", evidence_root, events_rel, False, ambiguous))

    report = {"v": CONTRACT_VERSION,
              "subject": {"repository_id": repository_id, "kit_path": kit_path},
              "sources": [], "reads": {"selected": 0, "opened": 0, "bytes": 0},
              "coverage": {"complete": True, "stopped_by": None,
                           "absent": [name for name, selected in (("graph", graph_path),
                                                                   ("attempt-events", binding))
                                      if selected is None]},
              "limits": cfg}
    sp = _sibling("safe_paths")
    for kind, root, rel, structural, ambiguous in selection:
        if report["reads"]["selected"] >= cfg["max_sources"]:
            report["coverage"].update(complete=False, stopped_by="max_sources")
            break
        report["reads"]["selected"] += 1
        if ambiguous:
            source = _observation(kind, "unavailable", reason_code="ambiguous-binding")
        elif not _eligible(rel, denied, structural_kit=structural):
            source = _observation(kind, "forbidden", reason_code="forbidden")
        else:
            budget = cfg["max_total_bytes"] - report["reads"]["bytes"]
            if budget <= 0:
                source = _observation(kind, "over-limit", reason_code="max_total_bytes")
            else:
                try:
                    result = sp.confined_read_stable_bytes(root, rel,
                        max_bytes=cfg["max_source_bytes"], read_budget=budget)
                except sp.SourceReadError as exc:
                    report["reads"]["opened"] += exc.opened
                    report["reads"]["bytes"] += exc.bytes_read
                    state = exc.reason_code if exc.reason_code in (
                        "missing", "forbidden", "inconsistent", "over-limit", "unavailable") \
                        else "unavailable"
                    source = _observation(kind, state, reason_code=exc.reason_code)
                else:
                    report["reads"]["opened"] += result["opened"]
                    report["reads"]["bytes"] += result["bytes_read"]
                    raw = result["data"]
                    if kind == "attempt-events" and result["links"] > 1:
                        source = _observation(kind, "unavailable", reason_code="ambiguous-inode")
                    else:
                        version = (_sibling("kit_contract").CONTRACT_VERSION
                                   if kind == "kit:TASKS.md" else
                                   _sibling("attempt_ledger").LEDGER_VERSION
                                   if kind == "attempt-events" else None)
                        ref = _source_ref(repository_id, kit_path, kind, rel, raw, version)
                        try:
                            observed, items, redactions, exclusions = _selected_observed(
                                kind, raw, cfg["max_items"], denied)
                            retained = len(json.dumps(observed, ensure_ascii=False).encode("utf-8"))
                            if retained > cfg["max_source_bytes"]:
                                raise SourceLimitError("retained source exceeds limit")
                        except SourceLimitError:
                            source = _observation(kind, "over-limit", ref=ref,
                                consistency="consistent-at-read", reason_code="max_items-or-output")
                        except (UnicodeError, ValueError, RecursionError, TypeError):
                            source = _observation(kind, "corrupt", ref=ref,
                                consistency="consistent-at-read", reason_code="parse-refused")
                        else:
                            source = _observation(kind, "ok", ref=ref, observed=observed,
                                consistency="consistent-at-read", items=items,
                                retained_bytes=retained, redactions=redactions,
                                exclusions=exclusions)
        report["sources"].append(source)
        if not source["coverage"]["complete"]:
            report["coverage"]["complete"] = False
    return report
