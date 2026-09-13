#!/usr/bin/env python3
"""Fresh, bounded, task-relevant grounding from a graphify graph.json.

WHAT WAS MEASURED before this module existed. `bin/graph_brief.py` summarised a graph.json
without asking whether the graph still described the tree in front of it: a synthetic graph
naming a deleted file briefed normally, with no word about freshness anywhere in its output.
Its hubs were centrality over the whole graph, which is not relevance to the task at hand;
its one exclusion was a hard-coded `tests/` prefix; and there was no path from "the graph
does not cover this" to "read the code instead".

WHAT THIS MODULE DOES, AND DOES NOT. graphify stays optional, external, and never invoked
here: every code path reads a graph.json a human already produced. Beside that file this
module can write ONE artefact, a provenance sidecar (`stamp`), recorded from what is actually
available -- the graph's own bytes, the repository's revision and dirty set, a content
fingerprint per covered file, whatever metadata the graph carries -- and never an invented
extractor claim. A graph with no sidecar reports freshness UNKNOWN; a verified revision is
never manufactured. `freshness` compares the sidecar against the working tree, dirty and
untracked files included. `impact` walks the graph from seeds -- changed files or named
symbols -- under a depth bound, a node bound, and a hub rule: a node whose degree exceeds
the hub threshold is listed and never expanded through, because a hub reached in one hop is
not evidence of relevance. `search` is the fallback when there is no graph, the graph is
stale or unknown, a seed matches nothing, or coverage is weak: a bounded substring scan of
the tracked tree. `grounding` composes them into ONE result shape every harness adapter can
attach to a prompt, and `render_grounding` bounds that text.

WHAT THE GRAPH IS NOT. Code relationships are not the execution DAG (`bin/kit_contract.py`
holds that). Absence of an edge is never absence of a dependency; AST edges say nothing
about dynamic imports, and every result says so. Graph text, labels, and paths are untrusted
repository evidence: a path is used only after `bin/safe_paths.py` accepts it as a relative,
traversal-free component list under the repository root, a label is bounded before it is
rendered, and nothing here grants a permission, edits an acceptance criterion, or claims a
concurrent write is safe. Test-directory exclusions are an argument, not an assumption.

Git is reached only through `bin/proc_runner.py`, with read-only verbs, a wall-clock bound,
and an injectable seam, so the module carries no process-spawning primitive of its own.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

CONTRACT_VERSION = "polytropos.grounding/1"
SIDECAR_VERSION = "polytropos.graph-provenance/1"
SIDECAR_NAME = "graph.provenance.json"

FRESHNESS = ("fresh", "partial", "stale", "unknown")
FILE_STATES = ("unchanged", "changed", "deleted", "unfingerprinted", "rejected")
EXTRACTION_LABELS = ("commit-only", "working-tree", "unknown")

#: The only git verbs this module runs. Every one reads; none writes the tree or the index.
GIT_READ_VERBS = ("rev-parse", "status", "ls-files", "config")
GIT_TIMEOUT_SECONDS = 60

#: Input bounds. A graph past the byte ceiling is refused, not truncated; a covered file past
#: the file ceiling is left unfingerprinted and says so.
MAX_GRAPH_BYTES = 128 * 1024 * 1024
MAX_FINGERPRINT_FILES = 5000
MAX_FILE_BYTES = 8 * 1024 * 1024

#: Traversal and output bounds, all arguments with these defaults.
DEFAULT_DEPTH = 2
DEFAULT_LIMIT = 40
DEFAULT_HUB_DEGREE = 25
DEFAULT_MAX_CHARS = 6000
LABEL_CHARS = 120

SEARCH_MAX_FILES = 4000
SEARCH_MAX_HITS = 40
SEARCH_MAX_FILE_BYTES = 2 * 1024 * 1024
#: graphify's own output directory is never code; a search never answers from it.
SEARCH_ALWAYS_EXCLUDES = ("graphify-out/",)

#: Coverage limits every result states, whatever the graph says.
KNOWN_LIMITS = (
    "AST extraction does not see dynamic imports (importlib, plugin registries); a missing "
    "edge is never evidence of a missing dependency",
    "code relationships are navigation, not the execution DAG; they authorise no write and "
    "change no acceptance criterion",
    "a hub reached in one hop is listed, not expanded: centrality is not task relevance",
)

ADVISORY = ("graph metadata may suggest what to read; it grants no permission, edits no "
            "acceptance requirement, and establishes no safe concurrent write")

#: Graph metadata keys that name the extractor, when graphify writes them. Copied when
#: present, reported `unknown` when not; never guessed.
EXTRACTOR_KEYS = ("version", "graphify_version", "extractor_version", "generated_at",
                  "generated", "created", "extractor")


class GroundingError(ValueError):
    """An input this module cannot ground from: an unreadable graph, an oversized one, a
    sidecar for a different graph, an unknown extraction label."""


# ---- sibling modules ----------------------------------------------------------------------------

_SIBLINGS = {}


def _sibling(name):
    if name not in _SIBLINGS:
        path = Path(__file__).resolve().with_name(f"{name}.py")
        spec = importlib.util.spec_from_file_location(f"polytropos_{name}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SIBLINGS[name] = module
    return _SIBLINGS[name]


def _gb():
    return _sibling("graph_brief")


def _sp():
    return _sibling("safe_paths")


def _pr():
    return _sibling("proc_runner")


def chars_per_token():
    """The repo's one token estimator, read from `bin/context_weight.py`."""
    return _sibling("context_weight").EST_CHARS_PER_TOKEN


# ---- git, read-only, through the process runner ------------------------------------------------

def _git(repo, *args, git=None):
    """Run one read-only git verb -> `(rc, text)`. `git` is the injectable seam: a callable
    taking the argument list and returning `(rc, text)`, used by tests and the demo."""
    if args[0] not in GIT_READ_VERBS:
        raise GroundingError(f"git verb {args[0]!r} is not a read-only probe this module runs")
    if git is not None:
        return git(list(args))
    result = _pr().run(["git", "-C", str(repo), *args], cwd=repo,
                       timeout=GIT_TIMEOUT_SECONDS, name="git probe", text=False)
    rc = result.get("rc")
    out = result.get("stdout") or b""
    if rc is None:
        return 1, ""
    return rc, out.decode("utf-8", "replace")


def scrub_remote(url):
    """A remote URL with any credential removed; the host and path are identity enough."""
    if not url:
        return None
    if "://" in url:
        scheme, rest = url.split("://", 1)
        if "@" in rest.split("/", 1)[0]:
            rest = rest.split("@", 1)[1]
        return f"{scheme}://{rest}"
    return url


def _parse_status(text):
    """`git status --porcelain=v1 -z` output -> `(dirty, untracked)` sorted path lists."""
    dirty, untracked = [], []
    entries = text.split("\0")
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        if code == "??":
            untracked.append(path)
        else:
            dirty.append(path)
            if code[0] in "RC":
                i += 1  # a rename or copy carries its original path as the next entry
    return sorted(set(dirty)), sorted(set(untracked))


def repo_state(repo, git=None):
    """What git says about `repo` right now -> a dict; `available: False` with a reason when
    git cannot answer (not a repository, git absent, a hung probe)."""
    rc, top = _git(repo, "rev-parse", "--show-toplevel", git=git)
    if rc != 0 or not top.strip():
        return {"available": False, "reason": "not a git repository, or git is unavailable",
                "root": str(Path(repo).resolve()), "head": None, "dirty": [],
                "untracked": [], "remote": None, "name": Path(repo).resolve().name}
    root = Path(top.strip())
    rc, head = _git(repo, "rev-parse", "HEAD", git=git)
    head = head.strip() if rc == 0 and head.strip() else None
    rc, status = _git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all",
                      git=git)
    dirty, untracked = _parse_status(status) if rc == 0 else ([], [])
    rc, remote = _git(repo, "config", "--get", "remote.origin.url", git=git)
    return {
        "available": True, "reason": None, "root": str(root), "head": head,
        "dirty": dirty, "untracked": untracked,
        "remote": scrub_remote(remote.strip()) if rc == 0 else None,
        "name": root.name,
    }


# ---- graph inputs, treated as untrusted ---------------------------------------------------------

def load_graph_bytes(graph_path):
    """The graph's bytes, its sha256, and its parsed data; refuses a graph past the ceiling."""
    path = Path(graph_path)
    try:
        raw = path.read_bytes()
    except OSError:
        return None, None, None, "missing"
    if len(raw) > MAX_GRAPH_BYTES:
        return None, None, None, (
            f"{path} is {len(raw)} bytes, past the {MAX_GRAPH_BYTES}-byte ceiling this "
            f"module reads; it is refused, not truncated"
        )
    data, error = _gb().load_graph(path)
    if error:
        return raw, None, None, error
    return raw, hashlib.sha256(raw).hexdigest(), data, None


def graph_files(data):
    """Every distinct `source_file` in the graph -> `(accepted, rejected)`.

    A path is accepted only as relative, traversal-free components (`safe_paths.safe_parts`);
    anything else -- absolute, drive-qualified, `..`, empty -- is rejected with its reason and
    is never read. The graph wrote those strings; the repository did not vouch for them.
    """
    sp = _sp()
    accepted, rejected, seen = [], {}, set()
    for node in _gb()._nodes_of(data):
        raw = node.get("source_file")
        if raw is None or raw in seen:
            continue
        seen.add(raw)
        try:
            parts = sp.safe_parts(str(raw), what="graph source_file")
        except sp.SafePathError as exc:
            rejected[str(raw)[:LABEL_CHARS]] = str(exc)
            continue
        accepted.append(str(PurePosixPath(*parts)))
    return sorted(accepted), rejected


def _excluded(rel, excludes):
    return any(rel == e.rstrip("/") or rel.startswith(e if e.endswith("/") else e + "/")
               for e in excludes)


def fingerprint(root, rel):
    """sha256 of the working-tree file at `rel` under `root` -> `(digest, reason)`; exactly
    one is None. Reads through the confined reader, so a link is refused, not followed."""
    sp = _sp()
    try:
        data = sp.confined_read_bytes(root, rel, what="graph fingerprint", missing_ok=True)
    except sp.SafePathError as exc:
        return None, f"rejected: {exc}"
    except OSError as exc:
        return None, f"unreadable: {exc}"
    if data is None:
        return None, "absent"
    if len(data) > MAX_FILE_BYTES:
        return None, f"too large ({len(data)} bytes > {MAX_FILE_BYTES})"
    return hashlib.sha256(data).hexdigest(), None


def _graph_metadata(data):
    """Scalar top-level keys graphify may have written, bounded; the extractor facts among
    them are copied, the rest kept so a reader can see what the file claimed."""
    meta = {}
    for key, value in data.items():
        if key in ("nodes", "links", "edges"):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            meta[str(key)[:40]] = value[:200] if isinstance(value, str) else value
        if len(meta) >= 40:
            break
    return meta


# ---- provenance sidecar ---------------------------------------------------------------------------

def stamp(repo, graph_path, extraction="unknown", excludes=(), now=None, git=None,
          write=True):
    """Record what is actually known about `graph_path` -> the sidecar dict (written beside
    the graph unless `write=False`).

    `extraction` is the operator's label for how the graph was built (`commit-only` for a
    `git archive` tree, `working-tree` for an in-place run) and defaults to `unknown`; it is
    never inferred. Fingerprints are of the working tree at stamp time, dirty files included,
    because that is the content the graph was extracted from when it was built in place.
    """
    if extraction not in EXTRACTION_LABELS:
        raise GroundingError(
            f"extraction label {extraction!r} is not one of {', '.join(EXTRACTION_LABELS)}"
        )
    graph_path = Path(graph_path)
    raw, sha, data, error = load_graph_bytes(graph_path)
    if error:
        raise GroundingError(f"cannot stamp {graph_path}: {error}")
    state = repo_state(repo, git=git)
    root = Path(state["root"])
    files, rejected = graph_files(data)
    fingerprints, unfingerprinted, excluded = {}, {}, []
    for rel in files[:MAX_FINGERPRINT_FILES]:
        if _excluded(rel, excludes):
            excluded.append(rel)
            continue
        digest, reason = fingerprint(root, rel)
        if digest is None:
            unfingerprinted[rel] = reason
        else:
            fingerprints[rel] = digest
    beyond = files[MAX_FINGERPRINT_FILES:]
    meta = _graph_metadata(data)
    extractor = {k: meta[k] for k in EXTRACTOR_KEYS if k in meta}
    stamped_at = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        mtime = datetime.fromtimestamp(graph_path.stat().st_mtime, timezone.utc)
        graph_mtime = mtime.strftime("%Y-%m-%dT%H:%M:%SZ")
    except OSError:
        graph_mtime = None
    nodes = _gb()._nodes_of(data)
    links = _gb()._links_of(data)
    sidecar = {
        "v": SIDECAR_VERSION,
        "stamped_at": stamped_at,
        "graph": {"path": graph_path.name, "sha256": sha, "bytes": len(raw),
                  "nodes": len(nodes), "links": len(links),
                  "mtime": graph_mtime,
                  "mtime_note": "the graph file's modification time, not an extractor claim"},
        "repository": {"name": state["name"], "remote": state["remote"],
                       "git_available": state["available"]},
        "revision": {"head": state["head"], "dirty_at_stamp": state["dirty"],
                     "untracked_at_stamp": state["untracked"],
                     "note": None if state["available"] else state["reason"]},
        "extractor": {"name": "graphify", "source": "graph.json metadata" if extractor
                      else "unknown", **extractor},
        "extraction": extraction,
        "relationship_provenance": {
            "relations": dict(_gb().compute_relation_mix(links)),
            "confidence": dict(_gb().compute_confidence_mix(links)),
        },
        "coverage": {
            "files_in_graph": len(files),
            "files_fingerprinted": len(fingerprints),
            "files_unfingerprinted": unfingerprinted,
            "files_excluded": excluded,
            "files_beyond_ceiling": len(beyond),
            "paths_rejected": rejected,
            "excludes": list(excludes),
            "limits": list(KNOWN_LIMITS),
        },
        "graph_metadata": meta,
        "fingerprints": fingerprints,
    }
    if write:
        _sp().confined_write_bytes(
            graph_path.parent, SIDECAR_NAME,
            (json.dumps(sidecar, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            what="graph provenance sidecar", mode=0o600,
        )
    return sidecar


def read_sidecar(graph_path):
    """The sidecar beside `graph_path` -> `(sidecar, reason)`; exactly one is None."""
    sp = _sp()
    try:
        raw = sp.confined_read_bytes(Path(graph_path).parent, SIDECAR_NAME,
                                     what="graph provenance sidecar", missing_ok=True)
    except sp.SafePathError as exc:
        return None, f"provenance sidecar unreadable: {exc}"
    if raw is None:
        return None, (f"no provenance sidecar ({SIDECAR_NAME}) beside the graph; run "
                      f"`graph_ground.py stamp` after building it")
    try:
        sidecar = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        return None, f"provenance sidecar unreadable: {exc}"
    if not isinstance(sidecar, dict) or sidecar.get("v") != SIDECAR_VERSION:
        return None, (f"provenance sidecar is not {SIDECAR_VERSION}; freshness cannot be "
                      f"read from it")
    return sidecar, None


# ---- freshness against the working tree ---------------------------------------------------------

def freshness(repo, graph_path, git=None):
    """Does the graph still describe the tree? -> a verdict dict with `verdict` in
    `FRESHNESS`, per-file states, the revision facts, and every reason in words.

      fresh    a sidecar exists, git answered, and every fingerprinted file is unchanged.
      partial  some covered files changed or were deleted; the rest of the graph stands.
      stale    the graph.json bytes are not the ones the sidecar describes, or every covered
               file differs.
      unknown  no sidecar, an unreadable one, or git cannot answer -- file existence is still
               checked, so a graph naming deleted files says so even without provenance.
    """
    graph_path = Path(graph_path)
    raw, sha, data, error = load_graph_bytes(graph_path)
    if error == "missing":
        return _verdict("unknown", [f"no graph at {graph_path}"], graph_path)
    if error:
        return _verdict("unknown", [error], graph_path)
    sidecar, reason = read_sidecar(graph_path)
    state = repo_state(repo, git=git)
    root = Path(state["root"])
    files, rejected = graph_files(data)
    reasons = []
    if reason:
        reasons.append(reason)
    if not state["available"]:
        reasons.append(f"{state['reason']}: no revision to compare against; file existence "
                       f"checked only")
    recorded = (sidecar or {}).get("fingerprints") or {}
    states, changed, deleted, dirty_now = {}, [], [], []
    for rel in files:
        digest, why = fingerprint(root, rel)
        if digest is None and why == "absent":
            states[rel] = "deleted"
            deleted.append(rel)
            continue
        if digest is None:
            states[rel] = "rejected" if why.startswith("rejected") else "unfingerprinted"
            continue
        if rel in state["dirty"] or rel in state["untracked"]:
            dirty_now.append(rel)
        known = recorded.get(rel)
        if known is None:
            states[rel] = "unfingerprinted"
        elif known != digest:
            states[rel] = "changed"
            changed.append(rel)
        else:
            states[rel] = "unchanged"
    revision = {
        "stamped": (sidecar or {}).get("revision", {}).get("head"),
        "now": state["head"],
    }
    revision["moved"] = bool(revision["stamped"] and revision["now"]
                             and revision["stamped"] != revision["now"])
    if revision["moved"]:
        reasons.append(f"revision moved {revision['stamped'][:12]} -> {revision['now'][:12]}"
                       f" since the stamp; the per-file comparison below decides")
    if sidecar and sidecar.get("graph", {}).get("sha256") != sha:
        verdict = "stale"
        reasons.append("graph.json is not the file the sidecar describes (sha256 differs); "
                       "stamp it again")
    elif sidecar is None or not state["available"]:
        verdict = "unknown"
    elif deleted or changed:
        compared = [r for r in files if states.get(r) in ("unchanged", "changed", "deleted")]
        verdict = "stale" if compared and len(changed) + len(deleted) == len(compared) \
            else "partial"
        if deleted:
            reasons.append(f"{len(deleted)} covered file(s) no longer exist: "
                           + ", ".join(deleted[:8]) + (" ..." if len(deleted) > 8 else ""))
        if changed:
            reasons.append(f"{len(changed)} covered file(s) changed since the stamp: "
                           + ", ".join(changed[:8]) + (" ..." if len(changed) > 8 else ""))
    else:
        verdict = "fresh"
    if deleted and verdict == "unknown":
        reasons.append(f"{len(deleted)} of {len(files)} graph file(s) are absent from the "
                       f"working tree: " + ", ".join(deleted[:8]))
    if dirty_now:
        reasons.append(f"{len(dirty_now)} covered file(s) are dirty or untracked right now: "
                       + ", ".join(dirty_now[:8]) + (" ..." if len(dirty_now) > 8 else ""))
    uncovered = sorted(set(state["dirty"]) | set(state["untracked"])) if state["available"] \
        else []
    uncovered = [p for p in uncovered if p not in states]
    result = _verdict(verdict, reasons, graph_path)
    result.update({
        "sidecar": bool(sidecar),
        "extraction": (sidecar or {}).get("extraction", "unknown"),
        "stamped_at": (sidecar or {}).get("stamped_at"),
        "revision": revision,
        "git_available": state["available"],
        "files": states,
        "changed": changed,
        "deleted": deleted,
        "dirty_now": dirty_now,
        "uncovered_changed": uncovered[:50],
        "paths_rejected": rejected,
        "counts": {"in_graph": len(files), "fingerprinted": sum(1 for s in states.values()
                                                                if s in ("unchanged", "changed")),
                   "changed": len(changed), "deleted": len(deleted)},
    })
    return result


def _verdict(verdict, reasons, graph_path):
    return {"verdict": verdict, "reasons": list(reasons), "graph": str(graph_path)}


# ---- bounded impact -------------------------------------------------------------------------------

def _label(node):
    text = node.get("label") or node.get("norm_label") or str(node.get("id"))
    text = str(text).replace("\n", " ")
    return text[:LABEL_CHARS]


def impact(data, seeds, depth=DEFAULT_DEPTH, limit=DEFAULT_LIMIT,
           hub_degree=DEFAULT_HUB_DEGREE, excludes=(), file_states=None):
    """Neighbours of `seeds` in the graph, bounded -> a dict.

    A seed matches a node id, a label, or a `source_file` (every node in that file). The
    walk is breadth-first over both edge directions, stops at `depth`, stops adding once
    `limit` nodes are listed (`truncated` says so), never enters a file under an `excludes`
    prefix, and never expands THROUGH a hub: a node whose degree exceeds `hub_degree` is
    reported with that degree and its neighbours are not enqueued. Every neighbour carries
    the edge that reached it and the freshness state of its file when `file_states` is given.
    """
    gb = _gb()
    nodes = gb._nodes_of(data)
    links = gb._links_of(data)
    index = gb._node_index(nodes)
    degree = gb._degrees(nodes, links)
    adjacency = {}
    for link in links:
        s, t = link.get("source"), link.get("target")
        if s is None or t is None:
            continue
        edge = (link.get("relation") or "(none)", link.get("confidence") or "(none)")
        adjacency.setdefault(s, []).append((t, edge, "out"))
        adjacency.setdefault(t, []).append((s, edge, "in"))

    def excluded(node_id):
        node = index.get(node_id) or {}
        return _excluded(str(node.get("source_file") or ""), excludes)

    resolved, unmatched = {}, []
    for seed in seeds:
        matches = []
        if seed in index:
            matches.append(seed)
        for node_id, node in index.items():
            if node_id in matches:
                continue
            if seed in (node.get("label"), node.get("norm_label")) or \
                    str(node.get("source_file") or "") == seed:
                matches.append(node_id)
        matches = [m for m in matches if not excluded(m)]
        if matches:
            resolved[seed] = matches
        else:
            unmatched.append(seed)

    parents, order, seen = {}, [], set()
    frontier = []
    for seed, ids in resolved.items():
        for node_id in ids:
            if node_id not in seen:
                seen.add(node_id)
                parents[node_id] = None
                frontier.append((node_id, 0))
    neighbours, hubs, truncated, excluded_count = [], [], False, 0
    while frontier:
        node_id, d = frontier.pop(0)
        node = index.get(node_id) or {}
        is_seed = parents.get(node_id) is None
        is_hub = degree.get(node_id, 0) > hub_degree and not is_seed
        if not is_seed:
            if len(neighbours) >= limit:
                truncated = True
                break
            via = parents[node_id]
            path = []
            cur = node_id
            while cur is not None:
                path.append(cur)
                cur = parents[cur][0] if parents.get(cur) else None
            path.reverse()
            rel = str(node.get("source_file") or "")
            neighbours.append({
                "id": node_id, "label": _label(node), "source_file": rel or None,
                "source_location": node.get("source_location"), "depth": d,
                "degree": degree.get(node_id, 0), "hub": is_hub,
                "via": {"from": via[0], "relation": via[1][0], "confidence": via[1][1],
                        "direction": via[2]},
                "path": path,
                "file_state": (file_states or {}).get(rel, "unknown") if rel else None,
            })
            if is_hub:
                hubs.append(node_id)
                continue
        if d >= depth:
            continue
        for other, edge, direction in adjacency.get(node_id, ()):
            if other in seen:
                continue
            if excluded(other):
                excluded_count += 1
                continue
            seen.add(other)
            parents[other] = (node_id, edge, direction)
            frontier.append((other, d + 1))
    return {
        "seeds": resolved, "unmatched": unmatched, "neighbors": neighbours,
        "hubs_not_expanded": hubs, "truncated": truncated,
        "excluded": excluded_count,
        "bounds": {"depth": depth, "limit": limit, "hub_degree": hub_degree,
                   "excludes": list(excludes)},
    }


# ---- code-search fallback --------------------------------------------------------------------------

def _tracked_files(repo, state, git=None):
    """Files to search: git's tracked plus untracked-not-ignored list, or a bounded walk."""
    if state["available"]:
        rc, listing = _git(repo, "ls-files", "-z", "--cached", "--others",
                           "--exclude-standard", git=git)
        if rc == 0:
            return [p for p in listing.split("\0") if p]
    out = []
    root = Path(state["root"])
    for path in sorted(root.rglob("*")):
        if ".git" in path.parts or not path.is_file():
            continue
        out.append(str(path.relative_to(root).as_posix()))
        if len(out) >= SEARCH_MAX_FILES:
            break
    return out


def search(repo, terms, excludes=(), max_files=SEARCH_MAX_FILES, max_hits=SEARCH_MAX_HITS,
           git=None, skip=()):
    """A bounded substring scan of the repository for `terms` -> hits as path:line:text.

    Reads through the confined reader under the repository root, skips binary files, files
    past the size ceiling, and the exact paths in `skip` (the graph and its sidecar, so the
    graph never answers a search about itself), honours `excludes`, and stops at `max_hits`
    with `truncated` set. Plain text matching: no regular expression is built from a term
    the graph or a task wrote.
    """
    state = repo_state(repo, git=git)
    root = Path(state["root"])
    sp = _sp()
    terms = [t for t in terms if t]
    hits, scanned, truncated = [], 0, False
    if not terms:
        return {"terms": [], "files_scanned": 0, "hits": [], "truncated": False}
    for rel in _tracked_files(repo, state, git=git):
        if scanned >= max_files:
            truncated = True
            break
        if _excluded(rel, tuple(excludes) + SEARCH_ALWAYS_EXCLUDES) or rel in skip:
            continue
        try:
            data = sp.confined_read_bytes(root, rel, what="code search", missing_ok=True)
        except sp.SafePathError:
            continue
        if data is None or len(data) > SEARCH_MAX_FILE_BYTES or b"\0" in data[:1024]:
            continue
        scanned += 1
        text = data.decode("utf-8", "replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for term in terms:
                if term in line:
                    hits.append({"path": rel, "line": lineno, "term": term,
                                 "text": line.strip()[:LABEL_CHARS]})
                    if len(hits) >= max_hits:
                        truncated = True
                        break
            if truncated:
                break
        if truncated:
            break
    return {"terms": terms, "files_scanned": scanned, "hits": hits, "truncated": truncated}


def _terms_from_seeds(seeds):
    terms = []
    for seed in seeds:
        stem = PurePosixPath(seed).stem if "/" in seed or "." in seed else seed
        for candidate in (seed, stem):
            if candidate and candidate not in terms and len(candidate) >= 3:
                terms.append(candidate)
    return terms


# ---- the shared result ----------------------------------------------------------------------------

def grounding(repo, graph_path, seeds=(), changed=False, depth=DEFAULT_DEPTH,
              limit=DEFAULT_LIMIT, hub_degree=DEFAULT_HUB_DEGREE, excludes=(), git=None):
    """Everything an adapter attaches to a task prompt, in one shape -> a dict.

    `changed=True` seeds the walk with the working tree's dirty and untracked files, so a
    task that touched files asks "what is near what I changed". The graph's role is stated:
    `evidence` when fresh or partial, `hints` when stale or unknown. The search fallback runs
    when there is no graph, the graph is stale or unknown, a seed matched nothing, or the
    graph's own cross-file visibility is weak; it is reported as a fallback, never as the
    graph's answer.
    """
    graph_path = Path(graph_path) if graph_path else None
    state = repo_state(repo, git=git)
    seeds = list(seeds)
    if changed:
        for rel in state["dirty"] + state["untracked"]:
            if rel not in seeds:
                seeds.append(rel)
    result = {
        "v": CONTRACT_VERSION,
        "repository": state["name"],
        "provider": "graphify",
        "graph": str(graph_path) if graph_path else None,
        "graph_role": "none",
        "seeds": seeds,
        "freshness": None,
        "impact": None,
        "fallback": {"used": False, "reasons": [], "search": None},
        "limits": list(KNOWN_LIMITS),
        "advisory": ADVISORY,
    }
    fallback_reasons = []
    data = None
    if graph_path is None or not graph_path.exists():
        result["provider"] = "none"
        fallback_reasons.append("no graph.json to read; graphify is optional and was not run")
    else:
        fresh = freshness(repo, graph_path, git=git)
        result["freshness"] = fresh
        _raw, _sha, data, error = load_graph_bytes(graph_path)
        if error:
            fallback_reasons.append(f"graph unreadable: {error}")
            data = None
        else:
            result["graph_role"] = "evidence" if fresh["verdict"] in ("fresh", "partial") \
                else "hints"
            if fresh["verdict"] in ("stale", "unknown"):
                fallback_reasons.append(f"graph freshness is {fresh['verdict']}: its edges "
                                        f"are navigation hints, not evidence")
            brief = _gb().build_brief(data, 0)
            if brief["low_cross_file_warning"]:
                fallback_reasons.append("weak coverage: " + brief["low_cross_file_warning_text"])
                result["limits"].append(brief["low_cross_file_warning_text"])
            imp = impact(data, seeds, depth=depth, limit=limit, hub_degree=hub_degree,
                         excludes=excludes, file_states=fresh.get("files"))
            result["impact"] = imp
            if imp["unmatched"]:
                fallback_reasons.append("seeds the graph does not cover: "
                                        + ", ".join(imp["unmatched"][:8]))
    if fallback_reasons:
        terms = _terms_from_seeds(
            (result["impact"] or {}).get("unmatched") or seeds if data is not None else seeds
        )
        skip = ()
        if graph_path is not None:
            try:
                rel = graph_path.resolve().relative_to(Path(state["root"]).resolve())
                skip = (rel.as_posix(), (rel.parent / SIDECAR_NAME).as_posix())
            except ValueError:
                skip = ()
        result["fallback"] = {
            "used": True, "reasons": fallback_reasons,
            "search": search(repo, terms, excludes=excludes, git=git, skip=skip) if terms
            else {"terms": [], "files_scanned": 0, "hits": [], "truncated": False,
                  "note": "no seeds to search for"},
        }
    return result


def render_grounding(result, max_chars=DEFAULT_MAX_CHARS):
    """The grounding as prompt text, bounded to `max_chars` with the cut stated."""
    lines = [f"grounding ({result['v']}): repository={result['repository']} "
             f"provider={result['provider']} graph_role={result['graph_role']}"]
    fresh = result.get("freshness")
    if fresh:
        lines.append(f"  freshness: {fresh['verdict']}"
                     + (f" (extraction: {fresh.get('extraction')})" if fresh.get("extraction")
                        else ""))
        for reason in fresh.get("reasons", []):
            lines.append(f"    - {reason}")
        rev = fresh.get("revision") or {}
        if rev.get("now"):
            lines.append(f"    revision now {rev['now'][:12]}"
                         + (f", stamped {rev['stamped'][:12]}" if rev.get("stamped") else
                            ", no stamped revision"))
    imp = result.get("impact")
    if imp:
        seeds = ", ".join(f"{s} -> {len(ids)} node(s)" for s, ids in imp["seeds"].items())
        lines.append(f"  impact: seeds {seeds or '(none matched)'}; bounds depth="
                     f"{imp['bounds']['depth']} limit={imp['bounds']['limit']} "
                     f"hub_degree={imp['bounds']['hub_degree']}")
        for n in imp["neighbors"]:
            loc = f"{n['source_file'] or '(no file)'}:{n['source_location'] or '-'}"
            state = f" [{n['file_state']}]" if n.get("file_state") else ""
            hub = f" HUB(degree {n['degree']}, not expanded)" if n["hub"] else ""
            lines.append(f"    d{n['depth']} {n['label']} {loc}{state} via "
                         f"{n['via']['relation']}/{n['via']['confidence']} from "
                         f"{n['via']['from']}{hub}")
        if imp["truncated"]:
            lines.append(f"    ... truncated at {imp['bounds']['limit']} node(s)")
        if imp["unmatched"]:
            lines.append(f"    unmatched seeds: {', '.join(imp['unmatched'])}")
    fb = result.get("fallback") or {}
    if fb.get("used"):
        lines.append("  fallback: code search (" + "; ".join(fb["reasons"]) + ")")
        srch = fb.get("search") or {}
        for hit in srch.get("hits", []):
            lines.append(f"    {hit['path']}:{hit['line']}: {hit['text']}")
        if srch.get("truncated"):
            lines.append("    ... search truncated")
        if not srch.get("hits"):
            lines.append("    (no hits)")
    lines.append("  limits:")
    for limit in result.get("limits", []):
        lines.append(f"    - {limit}")
    lines.append(f"  advisory: {result['advisory']}")
    text = "\n".join(lines)
    if len(text) > max_chars:
        cpt = chars_per_token()
        note = (f"\n[grounding truncated to {max_chars} chars (~{max_chars // cpt} tokens "
                f"est.); the full result is the --json form]")
        text = text[: max(0, max_chars - len(note))] + note
    return text


# ---- demo -----------------------------------------------------------------------------------------

def _fake_git(root, head="abc123def456", dirty=(), untracked=()):
    """A canned git for the demo: answers the four probes without a repository."""
    def git(args):
        verb = args[0]
        if verb == "rev-parse" and args[1] == "--show-toplevel":
            return 0, str(root) + "\n"
        if verb == "rev-parse":
            return 0, head + "\n"
        if verb == "status":
            entries = [f" M {p}" for p in dirty] + [f"?? {p}" for p in untracked]
            return 0, "\0".join(entries) + ("\0" if entries else "")
        if verb == "config":
            return 0, "https://user:token@example.invalid/org/demo.git\n"
        if verb == "ls-files":
            files = sorted(str(p.relative_to(root).as_posix()) for p in root.rglob("*")
                           if p.is_file() and ".git" not in p.parts)
            return 0, "\0".join(files) + "\0"
        return 1, ""
    return git


def _demo(out=None):
    out = out or sys.stdout

    def say(line=""):
        print(line, file=out)

    tmp = Path(tempfile.mkdtemp(prefix="graph_ground_demo_"))
    try:
        (tmp / "app").mkdir()
        (tmp / "app" / "main.py").write_text("def run():\n    return helper()\n")
        (tmp / "app" / "utils.py").write_text("def helper():\n    return 1\n")
        (tmp / "app" / "gone.py").write_text("def old():\n    return 0\n")
        (tmp / "spec").mkdir()
        (tmp / "spec" / "test_main.py").write_text("def test_run():\n    assert run()\n")
        graph = {
            "version": "demo-0.9", "directed": True,
            "nodes": [
                {"id": "app.main.run", "label": "run", "source_file": "app/main.py",
                 "source_location": "L1"},
                {"id": "app.utils.helper", "label": "helper", "source_file": "app/utils.py",
                 "source_location": "L1"},
                {"id": "app.gone.old", "label": "old", "source_file": "app/gone.py",
                 "source_location": "L1"},
                {"id": "spec.test_main.test_run", "label": "test_run",
                 "source_file": "spec/test_main.py", "source_location": "L1"},
                {"id": "hub.everything", "label": "everything", "source_file": "app/utils.py",
                 "source_location": "L9"},
                {"id": "/etc/passwd", "label": "escape", "source_file": "/etc/passwd"},
            ],
            "links": [
                {"source": "app.main.run", "target": "app.utils.helper", "relation": "calls",
                 "confidence": "EXTRACTED"},
                {"source": "spec.test_main.test_run", "target": "app.main.run",
                 "relation": "calls", "confidence": "EXTRACTED"},
                {"source": "app.gone.old", "target": "app.utils.helper", "relation": "calls",
                 "confidence": "INFERRED"},
            ] + [{"source": "hub.everything", "target": f"leaf{i}", "relation": "calls",
                  "confidence": "EXTRACTED"} for i in range(30)]
              + [{"source": "app.utils.helper", "target": "hub.everything",
                  "relation": "calls", "confidence": "EXTRACTED"}],
        }
        graph["nodes"] += [{"id": f"leaf{i}", "label": f"leaf{i}", "source_file": "app/leaves.py"}
                           for i in range(30)]
        (tmp / "app" / "leaves.py").write_text("# leaves\n")
        (tmp / "graphify-out").mkdir()
        gp = tmp / "graphify-out" / "graph.json"
        gp.write_text(json.dumps(graph))
        git = _fake_git(tmp)

        say("== a graph with no sidecar: freshness is unknown, and a rejected path is named ==")
        f = freshness(tmp, gp, git=git)
        say(f"  verdict={f['verdict']}")
        for r in f["reasons"]:
            say(f"    - {r}")
        say(f"  rejected paths: {f['paths_rejected']}")

        say()
        say("== stamp it, then it is fresh ==")
        side = stamp(tmp, gp, extraction="working-tree", excludes=("spec/",), git=git)
        say(f"  stamped_at={side['stamped_at']} head={side['revision']['head']} "
            f"remote={side['repository']['remote']} extractor={side['extractor']}")
        say(f"  fingerprinted={side['coverage']['files_fingerprinted']} "
            f"excluded={side['coverage']['files_excluded']} "
            f"rejected={list(side['coverage']['paths_rejected'])}")
        f = freshness(tmp, gp, git=git)
        say(f"  verdict={f['verdict']} revision_moved={f['revision']['moved']}")

        say()
        say("== change one covered file, delete another: partial, and each is named ==")
        (tmp / "app" / "main.py").write_text("def run():\n    return helper() + 1\n")
        (tmp / "app" / "gone.py").unlink()
        git = _fake_git(tmp, head="fedcba987654", dirty=("app/main.py",))
        f = freshness(tmp, gp, git=git)
        say(f"  verdict={f['verdict']}")
        for r in f["reasons"]:
            say(f"    - {r}")

        say()
        say("== impact from the changed file, bounded; the hub is listed, not expanded ==")
        g = grounding(tmp, gp, changed=True, excludes=("spec/",), git=git)
        say(render_grounding(g))

        say()
        say("== no graph at all: the fallback is a bounded code search ==")
        g = grounding(tmp, tmp / "absent" / "graph.json", seeds=("helper",), git=git)
        say(render_grounding(g))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---- command line ---------------------------------------------------------------------------------

def _common(p, graph=True):
    p.add_argument("--repo", default=".", help="repository root (default: cwd)")
    if graph:
        p.add_argument("--graph", default=_gb().DEFAULT_GRAPH_PATH,
                       help=f"graph.json (default: {_gb().DEFAULT_GRAPH_PATH})")
    p.add_argument("--exclude", action="append", default=[],
                   help="path prefix to leave out (repeatable; e.g. tests/ or spec/)")
    p.add_argument("--json", action="store_true", help="machine-readable output")


def build_parser():
    ap = argparse.ArgumentParser(
        prog="graph_ground.py",
        description="Provenance, freshness, bounded impact, and a code-search fallback over "
                    "a graphify graph.json. Reads only; `stamp` writes one sidecar beside the "
                    "graph. Never invokes graphify.",
    )
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("stamp", help="write the provenance sidecar beside graph.json")
    _common(p)
    p.add_argument("--extraction", default="unknown", choices=EXTRACTION_LABELS,
                   help="how the graph was built; never inferred (default: unknown)")
    p = sub.add_parser("freshness", help="does the graph still describe the tree? "
                                         "exit 0 fresh/partial, 1 stale, 3 unknown")
    _common(p)
    p = sub.add_parser("impact", help="bounded neighbours of seeds (files or symbols)")
    _common(p)
    p.add_argument("--seed", action="append", default=[], help="node id, label, or file")
    p.add_argument("--changed", action="store_true", help="seed with dirty/untracked files")
    p.add_argument("--depth", type=int, default=DEFAULT_DEPTH)
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    p.add_argument("--hub-degree", type=int, default=DEFAULT_HUB_DEGREE)
    p = sub.add_parser("search", help="the bounded code-search fallback on its own")
    _common(p, graph=False)
    p.add_argument("--term", action="append", required=True)
    p = sub.add_parser("ground", help="the shared grounding result: freshness + impact + "
                                      "fallback, as prompt text or JSON")
    _common(p)
    p.add_argument("--seed", action="append", default=[])
    p.add_argument("--changed", action="store_true")
    p.add_argument("--depth", type=int, default=DEFAULT_DEPTH)
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    p.add_argument("--hub-degree", type=int, default=DEFAULT_HUB_DEGREE)
    p.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    sub.add_parser("demo", help="synthetic tree and graph in a temp dir, canned git; "
                                "spends nothing, invokes nothing")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "demo":
        _demo()
        return 0
    try:
        if args.command == "stamp":
            side = stamp(args.repo, args.graph, extraction=args.extraction,
                         excludes=tuple(args.exclude))
            if args.json:
                print(json.dumps(side, indent=2, sort_keys=True))
            else:
                print(f"stamped {Path(args.graph).parent / SIDECAR_NAME}: head="
                      f"{side['revision']['head']} fingerprinted="
                      f"{side['coverage']['files_fingerprinted']}/"
                      f"{side['coverage']['files_in_graph']} extraction={side['extraction']}")
            return 0
        if args.command == "freshness":
            f = freshness(args.repo, args.graph)
            print(json.dumps(f, indent=2, sort_keys=True) if args.json else
                  f"freshness: {f['verdict']}\n" + "\n".join(f"  - {r}" for r in f["reasons"]))
            return {"fresh": 0, "partial": 0, "stale": 1, "unknown": 3}[f["verdict"]]
        if args.command == "search":
            s = search(args.repo, args.term, excludes=tuple(args.exclude))
            if args.json:
                print(json.dumps(s, indent=2, sort_keys=True))
            else:
                for hit in s["hits"]:
                    print(f"{hit['path']}:{hit['line']}: {hit['text']}")
                print(f"({s['files_scanned']} file(s) scanned"
                      + (", truncated" if s["truncated"] else "") + ")")
            return 0
        if args.command == "impact":
            _raw, _sha, data, error = load_graph_bytes(args.graph)
            if error:
                print(f"impact: {error}", file=sys.stderr)
                return 2
            seeds = list(args.seed)
            if args.changed:
                st = repo_state(args.repo)
                seeds += [p for p in st["dirty"] + st["untracked"] if p not in seeds]
            fr = freshness(args.repo, args.graph)
            imp = impact(data, seeds, depth=args.depth, limit=args.limit,
                         hub_degree=args.hub_degree, excludes=tuple(args.exclude),
                         file_states=fr.get("files"))
            print(json.dumps(imp, indent=2, sort_keys=True) if args.json else
                  render_grounding({"v": CONTRACT_VERSION, "repository": Path(args.repo).name,
                                    "provider": "graphify", "graph_role": "evidence",
                                    "freshness": fr, "impact": imp, "fallback": None,
                                    "limits": list(KNOWN_LIMITS), "advisory": ADVISORY}))
            return 0
        g = grounding(args.repo, args.graph, seeds=args.seed, changed=args.changed,
                      depth=args.depth, limit=args.limit, hub_degree=args.hub_degree,
                      excludes=tuple(args.exclude))
        print(json.dumps(g, indent=2, sort_keys=True) if args.json else
              render_grounding(g, max_chars=args.max_chars))
        return 0
    except GroundingError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
