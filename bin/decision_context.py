#!/usr/bin/env python3
"""D16 -- which files a failed attempt was not shown, as a bounded, versioned manifest.

The recovery experiment's arm C supplies "one bounded package of previously missing contract
context" before a same-model retry. This module builds THAT PACKAGE'S MANIFEST: a deterministic
artifact naming direct consumers, omitted interfaces, configuration and contract tests, each
with the navigation evidence that found it, the freshness of the tree it was read from, and an
honest account of what was excluded and what was withheld.

============================================================================================
 WHAT THIS MODULE IS NOT
============================================================================================
It is not a second graph reader. `bin/graph_ground.py` owns provenance, freshness, the bounded
impact walk and the code-search fallback, and `bin/graph_brief.py` owns the graph's own shape;
graphify itself is external, user-installed and invoked by NOTHING here or there. This module
calls that seam's public functions and composes them into a different object for a different
reader: `grounding()` composes prompt text for a harness adapter, and this composes a candidate
manifest with a CLOSED reason vocabulary that a policy can branch on. Nothing here opens a
graph, parses one, or decides freshness on its own.

It is not an authority. A manifest selects nothing, admits nothing, retries nothing and
approves nothing. `bin/decision_policy.py` owns selection; the coordinator rechecks capability,
privacy, eligibility and budget admission immediately before it acts, and a manifest is an
input to that check rather than a substitute for it.

============================================================================================
 A GRAPH EDGE IS NAVIGATION EVIDENCE, NEVER DEPENDENCY OR PARALLEL-WRITE AUTHORITY
============================================================================================
This is a fence, not a sentence, and it is built three ways.

  * THERE IS NO MEMBER TO SET. `CANDIDATE_KINDS` and `EVIDENCE_KINDS` are closed tuples and
    neither has a dependency member; every candidate carries `authority: None`. A reader
    looking for "A depends on B" finds no field that could hold it.
  * THE EXTRACTOR'S WORD IS QUOTED, NOT ADOPTED. An edge's own label rides under `edge_label`
    with `EDGE_LABEL_NOTE` beside it, bounded and never interpreted. `graphify` wrote that
    string; this module does not vouch for it, and a missing edge is never evidence of a
    missing relationship (AST extraction does not see dynamic imports).
  * A DEPENDENCY-SPELLED KEY IS REFUSED. `assert_no_dependency_claim` sweeps every manifest
    before it is returned, using the punctuation-reducing key match D09 established and D14
    used for causation. Its work is forward: D17 extends this seam, and a `depends_on` or a
    `safe_to_parallel` added to a candidate would turn navigation into an authorisation.

Absence of an edge establishes no safe parallelism, and sequential execution stays the default
(`tasks/kits/decision-improvement/PLAN.md`). The execution DAG lives in `bin/kit_contract.py`
and is a different graph entirely.

============================================================================================
 FRESHNESS INCLUDES UNCOMMITTED WORK, AND THAT IS WHY THE FALLBACK EXISTS
============================================================================================
The failure mode this module is built against is a graph extracted last week that describes a
tree nobody has committed to since. A verdict of `partial` can hide it: every file the graph
covers may be unchanged while the work that actually broke sits in a file the graph never saw.
So `uncovered-dirty-context` -- a dirty or untracked path the graph does not cover -- is its own
retrieval reason and its own search trigger, beside the three obvious ones (no graph, a graph
that is stale or unknown, a seed the graph does not contain). `RETRIEVAL_REASONS` is the whole
vocabulary and every entry is recorded on the manifest.

============================================================================================
 PRIVACY IS WITHHELD VISIBLY, BY KIND AND COUNT, NEVER BY VALUE
============================================================================================
A privacy-ineligible file never becomes a candidate, and the manifest says how many were
withheld under which rule -- never the path, never a line of the content. `PRIVACY_RULE_KINDS`
is closed; `denied` EXTENDS the policy and no argument removes a rule. Two layers, because they
promise different things:

  * PREVENTION, WHERE A FILE WOULD BE OPENED. The bounded scan reads files, so the prefix-
    expressible rules -- the personal stores `bin/runtime_data.py` declares, and the operator's
    own `denied` list -- are handed to it as excludes and those files are never opened.
  * VISIBLE WITHHOLDING, WHERE NOTHING WOULD BE OPENED. The graph walk reads node metadata the
    graph already wrote and opens nothing, so the full policy is applied to its results
    afterwards and the count rides on the manifest under its rule. Handing the privacy
    prefixes to the walk as well would make that count silently zero, which reads as "nothing
    was ineligible" -- the exact misreading this design is built to prevent.

BE PRECISE ABOUT THE ONE GAP. A rule that is NOT a prefix -- a credential-shaped suffix or
name, a dotted path -- cannot be handed to the scan, so the scan has already READ such a file
by the time its path is judged. What is guaranteed there is that neither its path nor any byte
of it reaches the manifest. Only the prefix layer prevents the read, and no sentence here
claims otherwise.

Every excerpt this module retains goes through `bin/redact.py` first, and its `redactions` ride
on the manifest as `{kind: count}`. That reports that something was caught without being enough
to reconstruct it; shape-matching cannot prove absence, and nothing here claims it does.

============================================================================================
 DETERMINISM
============================================================================================
Identical inputs produce byte-identical output. Nothing here iterates a set into a result, every
collection is sorted through a total order before it is emitted, and the manifest carries NO
wall clock of its own: `generated_at` is the caller's `now` or `None`. `canonical_bytes` is the
artifact, and `sha256` is its digest over every other field. A hash identifies content; it is
not protection against a worker that can rewrite the file.
"""

import datetime
import hashlib
import importlib.util
import json
import re
from pathlib import Path, PurePosixPath

#: This manifest's own schema, registered in `release_gate.VERSION_SOURCES`. Not the grounding
#: contract's and not the provenance sidecar's: a candidate row is a THIRD object, assembled
#: from both, and a reader holding one needs to know which field names apply to IT.
CONTEXT_VERSION = "polytropos.context-candidates/1"

#: What a candidate IS, exhaustively. Every member is a place to look; none is a relationship.
#: `direct-consumer` reached the seed along an inbound edge, `omitted-interface` sits on an
#: outbound one and was not already supplied, and the last two are found by convention over a
#: path because a graph of code symbols does not index configuration or name a contract test.
CANDIDATE_KINDS = ("direct-consumer", "omitted-interface", "configuration", "contract-test")

#: How a candidate was FOUND. Navigation evidence, and the whole of it.
EVIDENCE_KINDS = ("graph-edge-inbound", "graph-edge-outbound", "search-hit")

#: Which retrieval passes ran. Recorded in this order; `search` never masquerades as `graph`.
RETRIEVAL_SOURCES = ("graph", "search")

#: Why the bounded scan ran. Closed, so a policy can branch on a reason instead of on prose.
#: `kind-not-in-graph` is the honest one: asked for configuration or contract tests, the graph
#: offered none, and a scan is the only way to answer -- that is a fallback, not a graph answer.
RETRIEVAL_REASONS = (
    "graph-not-fresh",
    "graph-unreadable",
    "kind-not-in-graph",
    "no-graph",
    "seed-not-in-graph",
    "uncovered-dirty-context",
)

#: A manifest either names candidates or abstains. "No applicable context is a legitimate
#: abstention" (`tasks/kits/decision-improvement/PLAN.md`); it is not a failure and not an
#: empty success.
MANIFEST_STATUSES = ("candidates", "no-relevant-context")

#: Why an abstention happened, so "we found nothing" is never confused with "we found things
#: and could show you none of them".
ABSTENTION_REASONS = (
    "all-candidates-already-supplied",
    "all-candidates-hub",
    "all-candidates-withheld",
    "no-evidence-found",
    "no-seed-matched",
)

#: Privacy rule kinds, closed. `denied` adds prefixes under `operator-denied`; no argument
#: removes a rule, which is why there is no `allow` parameter anywhere in this module.
PRIVACY_RULE_KINDS = ("operator-denied", "runtime-store", "credential-shape", "dot-path")

CREDENTIAL_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".keystore", ".jks", ".asc")
CREDENTIAL_NAMES = (".env", ".netrc", ".npmrc", ".pypirc", "credentials", "id_rsa",
                    "id_ecdsa", "id_ed25519")

#: Classification conventions. Arguments with these defaults, never assumptions: a repository
#: that keeps its tests in `spec/` says so rather than being told it has none.
DEFAULT_TEST_PREFIXES = ("tests/", "test/", "spec/")
DEFAULT_TEST_NAME_PREFIX = "test_"
DEFAULT_TEST_NAME_SUFFIX = "_test"
DEFAULT_CONFIG_SUFFIXES = (".json", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".conf",
                           ".properties")

#: Retrieval bounds. Every one is an argument; these are the defaults and the ceilings that
#: bound the arguments themselves, because "bounded" that a caller can raise without limit is
#: not bounded.
DEFAULT_MAX_CANDIDATES = 12
DEFAULT_MAX_PER_KIND = 4
DEFAULT_DEPTH = 1
DEFAULT_EXCERPT_CHARS = 200
MAX_CANDIDATES_CEILING = 60
MAX_PER_KIND_CEILING = 30
MAX_DEPTH_CEILING = 3
MAX_EXCERPT_CEILING = 1000
MAX_SEEDS = 20
MAX_SUPPLIED = 200
MAX_TERMS = 12
MIN_TERM_CHARS = 3
GRAPH_NODE_LIMIT_FACTOR = 4
GRAPH_NODE_LIMIT_CEILING = 400
SEARCH_HIT_LIMIT_FACTOR = 4
SEARCH_HIT_LIMIT_CEILING = 200

#: Key spellings that would turn navigation into a claim. Compared with punctuation and case
#: removed, so `depends_on`, `DependsOn` and `depends.on` are one token.
DEPENDENCY_TOKENS = (
    "depends", "dependson", "dependency", "dependencies", "dependents", "dependedon",
    "requires", "requiredby", "prerequisite", "prerequisites", "blocks", "blockedby",
    "imports", "importedby", "uses", "usedby", "parallel", "parallelsafe", "parallelwrite",
    "safetoparallel", "canparallelize", "concurrentwrite", "writelock", "grants", "authorises",
    "authorizes", "permits",
)

NO_DEPENDENCY_CLAIM = (
    "a graph edge is navigation evidence: it says where to look next. It is not a dependency, "
    "it does not establish that one file needs another, and it authorises no concurrent write. "
    "A missing edge is not a missing relationship -- AST extraction does not see dynamic "
    "imports -- and the execution DAG is bin/kit_contract.py's, not this graph's"
)

EDGE_LABEL_NOTE = ("the extractor's own word for this edge, copied verbatim, bounded, and not "
                   "interpreted here")

ABSTENTION_NOTE = ("no applicable context is a legitimate answer: an empty candidate list is an "
                   "abstention with its reasons, never a failure and never an empty success")

WITHHELD_NOTE = ("privacy-ineligible files are reported by rule and count only. Neither the "
                 "path nor any byte of the content appears anywhere in this manifest. Rules "
                 "expressible as a path prefix are refused before the file is opened; the rest "
                 "are applied after a bounded scan has already read it")

LIMITS = (
    "a candidate is a place to read, chosen under a bounded retrieval policy; it is not a "
    "finding, a diagnosis, or evidence that reading it will help",
    "configuration and contract tests are matched by path convention, which is an argument "
    "here and not an assumption about how a repository is laid out",
    "shape-matching redaction reports what it caught by kind and count; it cannot prove that "
    "nothing sensitive got through",
)


# ---- sibling loaders (bin/ is not a package) -------------------------------------------------

_MODS = {}


def _sibling(name):
    if name not in _MODS:
        path = Path(__file__).resolve().parent / f"{name}.py"
        spec = importlib.util.spec_from_file_location(f"polytropos_ctx_{name}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _MODS[name] = mod
    return _MODS[name]


def _gg():
    """The graph/search seam. Provenance, freshness, the bounded walk and the scan are ITS."""
    return _sibling("graph_ground")


def _sp():
    return _sibling("safe_paths")


def _rd():
    return _sibling("redact")


def _contract():
    return _sibling("decision_contract")


def _refuse(code, message):
    """One refusal, in the decision contract's vocabulary rather than a second one beside it."""
    return _contract().ContractError(code, message)


# ---- the dependency fence --------------------------------------------------------------------

def _alnum(text):
    return re.sub(r"[^a-z0-9]+", "", text.lower())


_DEPENDENCY_ALNUM = frozenset(_alnum(token) for token in DEPENDENCY_TOKENS)


def _is_dependency_key(key):
    if not isinstance(key, str):
        return False
    if _alnum(key) in _DEPENDENCY_ALNUM:
        return True
    return any(_alnum(part) in _DEPENDENCY_ALNUM for part in key.split("."))


def assert_no_dependency_claim(value, where="the candidate manifest"):
    """Refuse a structure carrying a key spelled like "A depends on B" or "this is safe to
    write in parallel".

    Nearly free today, because no code path here can produce such a key. Its work is forward:
    D17 extends this seam, and a `depends_on` on a candidate would silently promote navigation
    evidence into a dependency claim -- and a `safe_to_parallel` would promote it into a
    write authorisation, which is the more dangerous of the two.
    """
    hits = []
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, sub in item.items():
                if _is_dependency_key(key):
                    hits.append(key)
                stack.append(sub)
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
    if hits:
        raise _refuse("authority-field",
                      f"{where} carries {', '.join(repr(h) for h in sorted(set(hits)))}. "
                      f"{NO_DEPENDENCY_CLAIM}")
    return value


# ---- the privacy policy ------------------------------------------------------------------------

def store_prefixes():
    """The personal stores, as path prefixes, read from their own declaring module.

    `bin/runtime_data.py` is the authority on which directories are personal data; naming them
    again here would be a second list to drift. A store directory is never context for a repair.
    """
    return tuple(f"{name}/" for name in sorted(_sibling("runtime_data").STORES))


def prefix_rules(denied=()):
    """Privacy rules expressible as a path prefix -> the prefixes handed to the BOUNDED SCAN
    as excludes, so a file under one is never opened. The graph walk is given the caller's own
    excludes only, so a privacy-ineligible node there is withheld visibly instead."""
    return tuple(sorted(set(tuple(denied) + store_prefixes())))


def privacy_rule(rel, denied=()):
    """Which privacy rule makes `rel` ineligible, or None. First match in `PRIVACY_RULE_KINDS`
    order, so the report is stable for a path that several rules would catch."""
    text = str(rel)
    if any(text == d.rstrip("/") or text.startswith(d if d.endswith("/") else d + "/")
           for d in denied):
        return "operator-denied"
    if any(text.startswith(p) for p in store_prefixes()):
        return "runtime-store"
    name = PurePosixPath(text).name
    lowered = name.lower()
    if lowered in CREDENTIAL_NAMES or any(lowered.endswith(s) for s in CREDENTIAL_SUFFIXES):
        return "credential-shape"
    if any(part.startswith(".") for part in PurePosixPath(text).parts):
        return "dot-path"
    return None


# ---- validation --------------------------------------------------------------------------------

def _strings(value, what, ceiling):
    if isinstance(value, (str, bytes)):
        raise _refuse("wrong-type", f"{what} must be a sequence of paths, not one string; "
                                    f"a bare string iterates one character at a time")
    if not isinstance(value, (list, tuple)):
        raise _refuse("wrong-type", f"{what} must be a list or tuple, not {type(value).__name__}")
    out = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise _refuse("value-invalid", f"{what} carries {item!r}, which is not a non-empty "
                                           f"string")
        out.append(item.strip())
    if len(out) > ceiling:
        raise _refuse("bounds-exceeded", f"{what} carries {len(out)} entries, past the "
                                         f"{ceiling} this module reads")
    return tuple(out)


def _bounded_int(value, what, ceiling):
    if isinstance(value, bool) or not isinstance(value, int):
        raise _refuse("wrong-type", f"{what} must be an int, not {type(value).__name__}")
    if value < 1 or value > ceiling:
        raise _refuse("bounds-exceeded", f"{what}={value} is outside 1..{ceiling}")
    return value


def _stamp(now):
    """`now` -> an instant string, or None. A zoneless datetime is refused rather than read as
    local time: every producer this manifest sits beside writes UTC."""
    if now is None:
        return None
    if not isinstance(now, datetime.datetime):
        raise _refuse("wrong-type", f"now must be a datetime, not {type(now).__name__}")
    if now.tzinfo is None:
        raise _refuse("value-invalid", "now carries no timezone; a zoneless instant would be "
                                       "read as this machine's local time")
    return now.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- classification ------------------------------------------------------------------------------

def classify(rel, direction, test_prefixes=DEFAULT_TEST_PREFIXES,
             test_name_prefix=DEFAULT_TEST_NAME_PREFIX,
             test_name_suffix=DEFAULT_TEST_NAME_SUFFIX,
             config_suffixes=DEFAULT_CONFIG_SUFFIXES):
    """Which `CANDIDATE_KINDS` member `rel` is, given how it was reached.

    Convention first -- a contract test and a configuration file are recognised by where they
    live and what they are called, whichever pass found them -- then the navigation direction:
    something that reached the seed is a consumer of it, something the seed reached is an
    interface the attempt was not shown. `direction` is `"in"`, `"out"` or None for a scan hit.
    """
    text = str(rel)
    name = PurePosixPath(text).name
    stem = PurePosixPath(name).stem
    if any(text.startswith(p if p.endswith("/") else p + "/") for p in test_prefixes) \
            or name.startswith(test_name_prefix) or stem.endswith(test_name_suffix):
        return "contract-test"
    if any(name.lower().endswith(s) for s in config_suffixes):
        return "configuration"
    if direction == "in":
        return "direct-consumer"
    return "omitted-interface"


def _terms(seeds):
    """Bounded search terms from the seeds: the seed itself and, for a path, its stem."""
    out = []
    for seed in seeds:
        stem = PurePosixPath(seed).stem if ("/" in seed or "." in seed) else seed
        for candidate in (seed, stem):
            if candidate and len(candidate) >= MIN_TERM_CHARS and candidate not in out:
                out.append(candidate)
        if len(out) >= MAX_TERMS:
            break
    return tuple(out[:MAX_TERMS])


def _safe_rel(raw):
    """A repository-relative path the seam's own path helper accepts, or None. The graph wrote
    these strings and the repository never vouched for them."""
    sp = _sp()
    try:
        parts = sp.safe_parts(str(raw), what="context candidate path")
    except sp.SafePathError:
        return None
    return str(PurePosixPath(*parts))


# ---- the manifest ----------------------------------------------------------------------------------

def context_manifest(repo, graph_path, *, seeds, supplied=(), kinds=CANDIDATE_KINDS,
                     max_candidates=DEFAULT_MAX_CANDIDATES,
                     max_per_kind=DEFAULT_MAX_PER_KIND, depth=DEFAULT_DEPTH,
                     hub_degree=None, excerpt_chars=DEFAULT_EXCERPT_CHARS,
                     excludes=(), denied=(), test_prefixes=DEFAULT_TEST_PREFIXES,
                     config_suffixes=DEFAULT_CONFIG_SUFFIXES, now=None, git=None):
    """The bounded context-candidate manifest for `seeds` -> a dict.

    `seeds` are the failed attempt's own subjects: the files it changed, or the symbols the
    failure named. `supplied` is what that attempt was ALREADY shown -- without it "omitted"
    would be decoration, since every interface would read as missing. `git` is the seam's
    injectable probe: supplied, nothing in this call starts a process.
    """
    gg = _gg()
    seeds = _strings(seeds, "seeds", MAX_SEEDS)
    if not seeds:
        raise _refuse("missing-field", "a manifest needs at least one seed to retrieve around")
    supplied = _strings(supplied, "supplied", MAX_SUPPLIED)
    excludes = _strings(excludes, "excludes", MAX_SUPPLIED)
    denied = _strings(denied, "denied", MAX_SUPPLIED)
    kinds = _strings(kinds, "kinds", len(CANDIDATE_KINDS))
    unknown = [k for k in kinds if k not in CANDIDATE_KINDS]
    if unknown:
        raise _refuse("unknown-value", f"kinds carries {sorted(unknown)!r}; the candidate kinds "
                                       f"are {', '.join(CANDIDATE_KINDS)}")
    if not kinds:
        raise _refuse("missing-field", "kinds is empty; a retrieval policy that wants nothing "
                                       "has nothing to bound")
    max_candidates = _bounded_int(max_candidates, "max_candidates", MAX_CANDIDATES_CEILING)
    max_per_kind = _bounded_int(max_per_kind, "max_per_kind", MAX_PER_KIND_CEILING)
    depth = _bounded_int(depth, "depth", MAX_DEPTH_CEILING)
    excerpt_chars = _bounded_int(excerpt_chars, "excerpt_chars", MAX_EXCERPT_CEILING)
    hub_degree = gg.DEFAULT_HUB_DEGREE if hub_degree is None else \
        _bounded_int(hub_degree, "hub_degree", 10_000)
    generated_at = _stamp(now)

    wanted = tuple(k for k in CANDIDATE_KINDS if k in kinds)
    # A seed is the thing under repair; handing it back as context it was "not shown" would be
    # a candidate that is always available and never useful.
    supplied_set = frozenset(supplied) | frozenset(seeds)
    prevented = prefix_rules(denied)
    # TWO EXCLUDE LISTS ON PURPOSE, and the difference is the privacy promise.
    # The graph walk opens no file -- it reads node metadata the graph already wrote -- so a
    # privacy-ineligible path there is WITHHELD below, visibly, with its rule and a count. The
    # bounded scan does open files, so the prefix rules go to it as excludes and those files
    # are never read at all. Prevention where a read would happen; visible withholding where
    # none would. Passing the privacy prefixes to the walk as well would make the walk's
    # withheld count silently zero, which reads as "nothing was ineligible".
    walk_excludes = tuple(sorted(set(excludes)))
    scan_excludes = tuple(sorted(set(excludes) | set(prevented)))

    state = gg.repo_state(repo, git=git)
    reasons, sources = set(), []
    excluded = {"hubs": 0, "already_supplied": 0, "rejected_paths": 0, "not_requested": 0,
                "duplicates": 0, "over_budget": 0}
    withheld_counts = {}
    redactions = {}
    rows = []

    def withhold(rule):
        withheld_counts[rule] = withheld_counts.get(rule, 0) + 1

    # ---- the graph pass ------------------------------------------------------------------
    graph_file = Path(graph_path) if graph_path else None
    fresh = None
    data = None
    graph_role = "none"
    if graph_file is None or not graph_file.exists():
        reasons.add("no-graph")
    else:
        fresh = gg.freshness(repo, graph_file, git=git)
        _raw, _sha, data, error = gg.load_graph_bytes(graph_file)
        if error:
            reasons.add("graph-unreadable")
            data = None
        else:
            graph_role = "evidence" if fresh["verdict"] in ("fresh", "partial") else "hints"
            if fresh["verdict"] in ("stale", "unknown"):
                reasons.add("graph-not-fresh")

    node_limit = min(max_candidates * GRAPH_NODE_LIMIT_FACTOR, GRAPH_NODE_LIMIT_CEILING)
    if data is not None:
        sources.append("graph")
        walk = gg.impact(data, list(seeds), depth=depth, limit=node_limit,
                         hub_degree=hub_degree, excludes=walk_excludes,
                         file_states=(fresh or {}).get("files"))
        if walk["unmatched"]:
            reasons.add("seed-not-in-graph")
        for neighbour in walk["neighbors"]:
            if neighbour["hub"]:
                excluded["hubs"] += 1
                continue
            rel = _safe_rel(neighbour.get("source_file") or "")
            if rel is None:
                excluded["rejected_paths"] += 1
                continue
            rule = privacy_rule(rel, denied)
            if rule is not None:
                withhold(rule)
                continue
            if rel in supplied_set:
                excluded["already_supplied"] += 1
                continue
            via = neighbour.get("via") or {}
            kind = classify(rel, via.get("direction"), test_prefixes=test_prefixes,
                            config_suffixes=config_suffixes)
            if kind not in wanted:
                excluded["not_requested"] += 1
                continue
            location = neighbour.get("source_location")
            rows.append({
                "kind": kind,
                "path": rel,
                "location": str(location)[:gg.LABEL_CHARS] if location else None,
                "symbol": str(neighbour.get("label") or "")[:gg.LABEL_CHARS] or None,
                "evidence": {
                    "kind": "graph-edge-inbound" if via.get("direction") == "in"
                    else "graph-edge-outbound",
                    "edge_label": str(via.get("relation") or "")[:gg.LABEL_CHARS] or None,
                    "edge_confidence": str(via.get("confidence") or "")[:gg.LABEL_CHARS] or None,
                    "edge_label_note": EDGE_LABEL_NOTE,
                    "neighbour_of": str(via.get("from") or "")[:gg.LABEL_CHARS] or None,
                    "hops": neighbour.get("depth"),
                    "degree": neighbour.get("degree"),
                },
                "excerpt": None,
                "file_state": neighbour.get("file_state") or "unknown",
                "authority": None,
                "note": NO_DEPENDENCY_CLAIM,
            })

    # ---- dirty and untracked work the graph does not cover -------------------------------
    if fresh is not None:
        uncovered = list(fresh.get("uncovered_changed") or [])
    else:
        uncovered = sorted(set(state["dirty"]) | set(state["untracked"]))
    if uncovered:
        reasons.add("uncovered-dirty-context")

    # ---- did the graph answer the kinds that were asked for? -----------------------------
    # Only meaningful when a graph was actually READ: the reason says "the graph offered none
    # of this kind", which is not a claim anyone can make about a graph that does not exist.
    if data is not None:
        found_kinds = {row["kind"] for row in rows}
        if any(k in ("configuration", "contract-test") and k not in found_kinds
               for k in wanted):
            reasons.add("kind-not-in-graph")

    # ---- the bounded scan ----------------------------------------------------------------
    # The scan is a FALLBACK and never a second opinion: a file the graph already named keeps
    # the kind the graph's own edge direction gave it, and the scan's hit in that same file is
    # dropped as a duplicate. Without this the same path arrives twice under two different
    # kinds -- once as the consumer an inbound edge proved, once as an "omitted interface" a
    # directionless hit assumed -- and the second reading is the weaker one.
    graph_paths = frozenset(row["path"] for row in rows)
    search_files, search_truncated = 0, False
    if reasons:
        sources.append("search")
        skip = ()
        if graph_file is not None:
            try:
                rel_graph = graph_file.resolve().relative_to(Path(state["root"]).resolve())
                skip = (rel_graph.as_posix(),
                        (rel_graph.parent / gg.SIDECAR_NAME).as_posix())
            except ValueError:
                skip = ()
        hit_limit = min(max_candidates * SEARCH_HIT_LIMIT_FACTOR, SEARCH_HIT_LIMIT_CEILING)
        found = gg.search(repo, list(_terms(seeds)), excludes=scan_excludes,
                          max_hits=hit_limit, git=git, skip=skip)
        search_files = found["files_scanned"]
        search_truncated = bool(found["truncated"])
        for hit in found["hits"]:
            rel = _safe_rel(hit.get("path") or "")
            if rel is None:
                excluded["rejected_paths"] += 1
                continue
            if rel in graph_paths:
                excluded["duplicates"] += 1
                continue
            rule = privacy_rule(rel, denied)
            if rule is not None:
                withhold(rule)
                continue
            if rel in supplied_set:
                excluded["already_supplied"] += 1
                continue
            kind = classify(rel, None, test_prefixes=test_prefixes,
                            config_suffixes=config_suffixes)
            if kind not in wanted:
                excluded["not_requested"] += 1
                continue
            cleaned = _rd().redact(hit.get("text") or "", limit=excerpt_chars)
            for name, count in cleaned["redactions"].items():
                redactions[name] = redactions.get(name, 0) + count
            rows.append({
                "kind": kind,
                "path": rel,
                "location": f"line {hit['line']}",
                "symbol": None,
                "evidence": {
                    "kind": "search-hit",
                    "term": str(hit.get("term") or "")[:gg.LABEL_CHARS] or None,
                    "line": hit.get("line"),
                },
                "excerpt": cleaned["text"],
                "file_state": (fresh or {}).get("files", {}).get(rel, "unknown"),
                "authority": None,
                "note": NO_DEPENDENCY_CLAIM,
            })

    # ---- one total order, then the budget -------------------------------------------------
    # A TOTAL order, and the last component is why. The graph walk's own order follows the
    # node list, so two runs over equal-but-differently-ordered graphs can reach the same file
    # from different parents; sorting on the fields a reader sees leaves those rows tied, and
    # a tie plus a stable sort means the INPUT order decides which one survives deduplication.
    # The canonical form of the whole row breaks every tie the same way every time.
    rows.sort(key=lambda row: (CANDIDATE_KINDS.index(row["kind"]), row["path"],
                               row["location"] or "", row["evidence"]["kind"],
                               row["symbol"] or "",
                               json.dumps(row, sort_keys=True, ensure_ascii=True)))
    unique, seen = [], set()
    for row in rows:
        key = (row["kind"], row["path"], row["location"], row["evidence"]["kind"])
        if key in seen:
            excluded["duplicates"] += 1
            continue
        seen.add(key)
        unique.append(row)
    kept, per_kind = [], {}
    for row in unique:
        if len(kept) >= max_candidates or per_kind.get(row["kind"], 0) >= max_per_kind:
            excluded["over_budget"] += 1
            continue
        per_kind[row["kind"]] = per_kind.get(row["kind"], 0) + 1
        kept.append(row)

    # ---- status and abstention ------------------------------------------------------------
    # An empty list with no reason beside it is the dishonest shape: it reads as "there was
    # nothing", when the truth may be "there was something and you may not see it". Every
    # reason that applies is recorded, and they stack.
    abstention = []
    if not kept:
        if withheld_counts:
            abstention.append("all-candidates-withheld")
        if excluded["hubs"]:
            abstention.append("all-candidates-hub")
        if excluded["already_supplied"]:
            abstention.append("all-candidates-already-supplied")
        if data is not None and "seed-not-in-graph" in reasons:
            abstention.append("no-seed-matched")
        if not abstention:
            abstention.append("no-evidence-found")
    status = "no-relevant-context" if not kept else "candidates"

    manifest = {
        "v": CONTEXT_VERSION,
        "generated_at": generated_at,
        "repository": state["name"],
        "seeds": sorted(seeds),
        "supplied": sorted(set(supplied)),
        "status": status,
        "abstention": sorted(set(abstention)),
        "abstention_note": ABSTENTION_NOTE,
        "bounds": {
            "kinds": list(wanted),
            "max_candidates": max_candidates,
            "max_per_kind": max_per_kind,
            "hops": depth,
            "hub_degree": hub_degree,
            "graph_node_limit": node_limit,
            "excerpt_chars": excerpt_chars,
            "excludes": sorted(set(excludes)),
            "denied_prefixes": list(prevented),
            "test_prefixes": sorted(set(test_prefixes)),
            "config_suffixes": sorted(set(config_suffixes)),
        },
        "retrieval": {
            "sources": [s for s in RETRIEVAL_SOURCES if s in sources],
            "reasons": sorted(reasons),
            "graph_role": graph_role,
            "files_scanned": search_files,
            "scan_truncated": search_truncated,
            "over_budget": excluded["over_budget"] > 0,
        },
        "freshness": {
            "verdict": (fresh or {}).get("verdict", "unknown"),
            "sidecar": bool((fresh or {}).get("sidecar")),
            "extraction": (fresh or {}).get("extraction", "unknown"),
            "git_available": bool(state["available"]),
            "revision": dict((fresh or {}).get("revision")
                             or {"stamped": None, "now": state["head"], "moved": False}),
            "changed": len((fresh or {}).get("changed") or []),
            "deleted": len((fresh or {}).get("deleted") or []),
            "dirty_now": len((fresh or {}).get("dirty_now") or []),
            "uncovered_changed": len(uncovered),
            "reasons": list((fresh or {}).get("reasons") or []),
        },
        "candidates": kept,
        "excluded": dict(sorted(excluded.items())),
        "withheld": [{"rule": rule, "count": withheld_counts[rule]}
                     for rule in PRIVACY_RULE_KINDS if rule in withheld_counts],
        "withheld_total": sum(withheld_counts.values()),
        "withheld_note": WITHHELD_NOTE,
        "redactions": dict(sorted(redactions.items())),
        "limits": list(LIMITS) + list(gg.KNOWN_LIMITS),
        "advisory": gg.ADVISORY,
        "navigation": NO_DEPENDENCY_CLAIM,
        "authority": None,
    }
    assert_no_dependency_claim(manifest)
    manifest["sha256"] = hashlib.sha256(canonical_bytes(manifest)).hexdigest()
    return manifest


def canonical_bytes(manifest):
    """The manifest's bytes, for the digest and for anything that stores or compares one.
    Sorted keys and no spare whitespace, so two equal manifests are byte-equal."""
    body = {key: value for key, value in manifest.items() if key != "sha256"}
    return (json.dumps(body, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True) + "\n").encode("utf-8")


def context_ref(manifest):
    """A reference another record can carry: version and digest, never the payload. A hash
    identifies content; it is not protection against a worker that can rewrite it."""
    if not isinstance(manifest, dict) or manifest.get("v") != CONTEXT_VERSION:
        raise _refuse("not-a-reference",
                      f"a context reference needs a {CONTEXT_VERSION} manifest")
    sha = manifest.get("sha256")
    if not isinstance(sha, str) or len(sha) != 64:
        raise _refuse("not-a-reference", "the manifest carries no digest to reference")
    return {"v": CONTEXT_VERSION, "sha": sha}


def render_manifest(manifest, max_chars=2000):
    """The manifest as bounded text, for a reader rather than a parser. Says where it cut."""
    lines = [f"context candidates ({manifest['v']}): repository={manifest['repository']} "
             f"status={manifest['status']} sha={manifest['sha256'][:12]}"]
    fresh = manifest["freshness"]
    lines.append(f"  freshness: {fresh['verdict']} (sidecar={fresh['sidecar']}, "
                 f"extraction={fresh['extraction']}, dirty_now={fresh['dirty_now']}, "
                 f"uncovered_changed={fresh['uncovered_changed']})")
    ret = manifest["retrieval"]
    lines.append(f"  retrieval: {', '.join(ret['sources']) or '(none)'}"
                 + (f" because {', '.join(ret['reasons'])}" if ret["reasons"] else ""))
    for row in manifest["candidates"]:
        lines.append(f"    [{row['kind']}] {row['path']}:{row['location'] or '-'} "
                     f"({row['evidence']['kind']}, file {row['file_state']})")
        if row["excerpt"]:
            lines.append(f"        {row['excerpt']}")
    if not manifest["candidates"]:
        lines.append(f"    (no candidates: {', '.join(manifest['abstention'])})")
    if manifest["withheld"]:
        lines.append("  withheld: " + ", ".join(f"{w['count']} under {w['rule']}"
                                                for w in manifest["withheld"]))
    if manifest["redactions"]:
        lines.append("  redacted: " + ", ".join(f"{k}={v}" for k, v in
                                                manifest["redactions"].items()))
    lines.append(f"  navigation: {manifest['navigation']}")
    text = "\n".join(lines)
    if len(text) > max_chars:
        note = f"\n[manifest text truncated to {max_chars} chars; the full artifact is the JSON]"
        text = text[: max(0, max_chars - len(note))] + note
    return text
