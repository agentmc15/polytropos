#!/usr/bin/env python3
"""D11 -- which policy bundle a run is entitled to read, and what it falls back to.

`bin/decision_contract.py` owns the RECORD: what a `PolicyBundle` and a `CandidateProposal` are,
and every refusal that makes one well formed. This module owns the SELECTION over those records:
given a pin, a catalog of bundle payloads and the facts a runtime can establish about itself,
which bundle's data parameters apply -- and, when none does, which fallback, and finally the
frozen legacy behaviour.

THIS MODULE IS A LIBRARY, NOT AN ENGINE, AND IT IS PURE.
It opens no file, writes nothing, starts no process, reads no home directory, has no CLI and
holds no state between calls. Every fact it reasons about arrives as an argument. That is not
style: the evaluation workbench is this repository's single owner of policy persistence, and a
second module that could write one would be a second writer of the same concern. Resolution is
the READ side and nothing else.

============================================================================================
 WHAT RESOLVING A BUNDLE DOES AND DOES NOT MEAN
============================================================================================
Selecting a bundle says "these data parameters are the ones in force for this cohort". It is
not an approval, a permission, a budget, an admission or an activation, and it cannot become
one: the fields that would say so are refused by the contract's `BANNED_FIELDS` before a bundle
parses at all, `BundleResolution` carries no mode and no grant, and every authority a run needs
is rechecked by the coordinator, freshly, immediately before it acts. A resolution is an input
to that check and never a substitute for it.

Nor does resolution ACTIVATE anything. Runtime activation -- moving a runtime from legacy to
canary or active -- is a separately gated transition owned by the workbench, behind evidence
this module does not have and does not ask for. With no pin supplied, resolution returns legacy,
which is the existing behaviour, which is the default everywhere until that gate says otherwise.

============================================================================================
 WHY EVERYTHING HERE TAKES PAYLOADS AND NOT PARSED OBJECTS
============================================================================================
`bin/` is not a package, so every module here is loaded by path, and two loaders of the same
file produce two module objects with two distinct sets of classes. A `PolicyBundle` built by one
loader fails `isinstance` against the other's class -- which is a real defect this kit has
already been bitten by, in a refusal whose `except` clause named a class object the raiser had
never heard of. So `resolve_bundle` takes bundle PAYLOADS, parses them through its own contract
instance, and returns objects from that instance. Dicts and digests cross a loader boundary
intact; classes do not. `bundle_ref` accepts either, because a content digest is a property of
the content and not of whoever parsed it.

============================================================================================
 THE FALLBACK CHAIN, AND WHERE IT STOPS
============================================================================================
A bundle that cannot be used hands off to its own declared fallback, which is either another
pinned bundle or the legacy behaviour. The walk is bounded by `MAX_FALLBACK_DEPTH`, refuses a
cycle, and always terminates: legacy is reachable from everywhere and needs nothing, so there is
no input for which this returns "no answer".

Three failures deliberately stop the walk instead of following the fallback -- an unknown id, a
payload that will not parse, and content whose digest does not match the pin that named it. In
all three the bundle's own fallback pointer is either missing or untrustworthy: a rewritten
bundle's idea of where to fall back to was written by whoever rewrote it. Those go straight to
legacy, which is the conservative end of the chain rather than a chosen one.
"""

import dataclasses
import hashlib
import importlib.util
import json
import types
from pathlib import Path

#: How many links of a fallback chain are walked before the walk gives up and returns legacy. A
#: chain this long is a lineage nobody is reading; the bound is here so a malformed catalog
#: cannot make resolution loop, and the cycle check below is what catches the ordinary mistake.
MAX_FALLBACK_DEPTH = 8

#: Where the parameters in force came from. `legacy` is not a bundle -- it is the absence of
#: one, and the frozen existing behaviour.
RESOLUTION_SOURCES = ("pinned", "fallback", "legacy")

#: Stable, machine-readable reasons a resolution came out the way it did. A caller branches on
#: these and a report counts them, so a rename silently empties somebody's tally. Every one of
#: them is an OBSERVATION about why a bundle was or was not used; none of them is a grant.
RESOLUTION_REASONS = (
    "approval-absent",
    "bundle-content-mismatch",
    "bundle-invalid",
    "bundle-unknown",
    "calibration-unmet",
    "capability-unverified",
    "component-mismatch",
    "fallback-cycle",
    "fallback-depth-exceeded",
    "fallback-legacy",
    "no-pin",
    "out-of-scope",
    "pin-not-a-reference",
    "provider-ineligible",
    "selected",
)
_REASON_SET = frozenset(RESOLUTION_REASONS)

#: What a caller must be able to say about the runtime before a bundle can be matched to it.
#: Every entry is a FACT SOMEONE ELSE ESTABLISHED: the capability registry says what is verified
#: (where unknown means no), the coordinator says which providers are eligible right now, and
#: the runtime says which contract versions it is actually running. This module establishes
#: none of them and cannot; it matches what it is told against what a bundle requires.
RUNTIME_KEYS = ("project", "task_class", "intended_use", "components", "capabilities",
                "providers", "calibration")

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


def _refuse(code, message):
    """One refusal, in the contract's own vocabulary rather than a second one beside it."""
    return _contract().ContractError(code, message)


# ---- identity -------------------------------------------------------------------------------

def bundle_ref(bundle):
    """The pinned reference that names this bundle's exact content.

    Built by `attempt_ledger.make_ref`, which owns what a reference IS, and carrying the
    BUNDLE's own contract version -- never the ledger's, which versions the event line rather
    than what the line points at, and never the decision contract's, which versions a different
    object entirely.

    Accepts a payload or a parsed bundle from any loader. A digest is a property of the content,
    so the reference is the same either way; this is the one place that accommodation is needed
    and it is deliberate.
    """
    contract = _contract()
    if isinstance(bundle, dict):
        bundle = contract.parse_bundle(bundle)
    identity = getattr(bundle, "id", None)
    digest = getattr(bundle, "sha", None)
    if not isinstance(identity, str) or not callable(digest):
        raise _refuse("wrong-type",
                      "bundle_ref takes a bundle payload or a parsed bundle; this is neither")
    return _al().make_ref(identity, sha=digest(), version=contract.BUNDLE_VERSION)


def matches_ref(bundle, ref):
    """Does this content still digest to what the reference pinned?

    False is the interesting answer: it means the bytes changed after somebody wrote down which
    bytes they meant. It does not mean tampering and it does not mean corruption -- a digest
    identifies content and diagnoses nothing. It means the pin and the content disagree, and
    that whatever depended on the pin should not proceed on the assumption that they agree.
    """
    ledger = _al()
    read = ledger.read_ref(ref)
    if read is None or read["sha"] is None:
        return False
    try:
        actual = bundle_ref(bundle)
    except (_contract().ContractError, ledger.RefError):
        # Content that will not parse is not the content the pin named. Narrow on purpose: a
        # TypeError out of here is a defect in the caller and must surface as itself rather
        # than be redressed as "the digests differ".
        return False
    return actual["id"] == read["id"] and actual["sha"] == read["sha"]


# ---- the runtime's own facts ----------------------------------------------------------------

def _runtime(value):
    """The facts a resolution is matched against, validated and frozen.

    Closed, like every other shape in this contract: an unknown fact is written as an explicit
    null or an empty list, so "nobody established it" can never look like "nobody wrote the
    key". An empty capability list means NOTHING is verified, which is the correct reading of an
    absent registry and the reason a bundle requiring a capability then falls back.
    """
    contract = _contract()
    if not isinstance(value, (dict, types.MappingProxyType)):
        raise _refuse("wrong-type",
                      f"the runtime facts must be an object, got {type(value).__name__}")
    extra = sorted(set(value) - set(RUNTIME_KEYS))
    if extra:
        raise _refuse("unknown-field",
                      f"the runtime facts have unknown field(s) "
                      f"{', '.join(repr(e) for e in extra)}")
    missing = sorted(key for key in RUNTIME_KEYS if key not in value)
    if missing:
        raise _refuse("missing-field",
                      f"the runtime facts are missing {', '.join(repr(m) for m in missing)}; "
                      f"an unestablished fact is written as an explicit null or empty list")
    for key in ("project", "task_class"):
        if not isinstance(value[key], str) or not value[key]:
            raise _refuse("value-invalid", f"the runtime's {key!r} must be a non-empty string")
    if value["intended_use"] not in contract.INTENDED_USES:
        raise _refuse("unknown-value",
                      f"the runtime's 'intended_use' is {value['intended_use']!r}; the "
                      f"vocabulary is {', '.join(contract.INTENDED_USES)}")
    components = value["components"]
    if not isinstance(components, dict):
        raise _refuse("wrong-type", "the runtime's 'components' must be an object")
    unknown = sorted(set(components) - set(contract.COMPONENT_KEYS))
    if unknown:
        raise _refuse("unknown-field",
                      f"the runtime's 'components' names {', '.join(repr(u) for u in unknown)}, "
                      f"which the bundle contract does not pin")
    for key in ("capabilities", "providers"):
        if not isinstance(value[key], (list, tuple)):
            raise _refuse("wrong-type", f"the runtime's {key!r} must be a list")
        for item in value[key]:
            if not isinstance(item, str) or not item:
                raise _refuse("value-invalid",
                              f"the runtime's {key!r} carries {item!r}; each entry is a name")
    calibration = value["calibration"]
    if calibration is not None and _al().read_ref(calibration) is None:
        raise _refuse("not-a-reference",
                      "the runtime's 'calibration' is neither null nor a reference")
    return types.MappingProxyType({
        "project": value["project"],
        "task_class": value["task_class"],
        "intended_use": value["intended_use"],
        "components": dict(components),
        "capabilities": tuple(value["capabilities"]),
        "providers": tuple(value["providers"]),
        "calibration": None if calibration is None else dict(_al().read_ref(calibration)),
    })


def runtime_facts(*, project, task_class, intended_use, components, capabilities=(),
                  providers=(), calibration=None):
    """The same object `_runtime` validates, built from named arguments instead of a dict.

    The arguments are handed over UNCOAERCED. An earlier version wrote `dict(components)` and
    `list(capabilities)` here, which answered the question before `_runtime` could ask it: a
    caller passing one capability id as a bare string got `list("codex-native-dispatch")` --
    twenty-one single-character capabilities -- instead of a refusal, and a caller passing a
    list of two-character strings for `components` got a dict built out of their letters.
    `_runtime` already type-checks both and already makes its own defensive copies from the
    values it validated, so coercing first could only ever hide a caller's mistake.
    """
    return _runtime({
        "project": project, "task_class": task_class, "intended_use": intended_use,
        "components": components, "capabilities": capabilities,
        "providers": providers, "calibration": calibration,
    })


# ---- resolution -----------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class BundleResolution:
    """Which parameters are in force, and the whole reason they are.

    There is deliberately no mode field, no approval field and no permission field on this
    object. Resolution reports what applies; it grants nothing, and a consumer that wanted a
    grant here would be reading it from the wrong authority. `bundle` is None exactly when
    `source` is `legacy`, and legacy is always reachable -- there is no input for which this
    object says "no answer".
    """

    source: str
    bundle: object
    ref: object
    chain: tuple
    reasons: tuple

    def __post_init__(self):
        # The two vocabularies above are what a caller branches on, so an undeclared value
        # cannot be constructed here at all -- the same rule `ContractError` applies to a
        # reason code, for the same reason: a code nobody declared is a code nobody counts.
        if self.source not in RESOLUTION_SOURCES:
            raise _refuse("unknown-value",
                          f"a resolution's source is {self.source!r}; the vocabulary is "
                          f"{', '.join(RESOLUTION_SOURCES)}")
        undeclared = sorted(set(self.reasons) - _REASON_SET)
        if undeclared:
            raise _refuse("unknown-value",
                          f"a resolution carries undeclared reason(s) "
                          f"{', '.join(repr(u) for u in undeclared)}")
        if (self.bundle is None) != (self.source == "legacy"):
            raise _refuse("value-invalid",
                          "a resolution carries a bundle exactly when it did not fall through "
                          "to legacy; these two disagree")

    @property
    def parameters(self):
        """The data parameters in force. Empty for legacy, which sets none of its own."""
        if self.bundle is None:
            return types.MappingProxyType({})
        return self.bundle.parameters

    def reason(self, code):
        return code in self.reasons


def _catalog(bundles):
    """Bundle payloads indexed by the id a pin would name them with.

    An entry carrying no string id is not indexable and so is unreachable by any pin; it is
    skipped rather than refused, because the catalog is whatever a caller has on hand and a
    payload from some other shape entirely -- the workbench's historical preference file, say --
    simply is not a bundle anybody can point at.
    """
    if isinstance(bundles, dict) or not isinstance(bundles, (list, tuple)):
        raise _refuse("wrong-type",
                      f"the catalog must be a list of bundle payloads, got "
                      f"{type(bundles).__name__}")
    out = {}
    for index, entry in enumerate(bundles):
        if not isinstance(entry, dict):
            raise _refuse("wrong-type",
                          f"catalog[{index}] must be an object, got {type(entry).__name__}")
        identity = entry.get("id")
        if isinstance(identity, str) and identity:
            out.setdefault(identity, entry)
    return out


def _unmet(bundle, facts):
    """Every requirement this bundle places that the runtime does not meet, all of them.

    Deliberately NOT short-circuited. A caller that is told only the first thing wrong fixes it
    and comes back for the next one, and -- the reason that matters here -- a test that asserts
    one specific reason cannot be satisfied by a different check happening to refuse the same
    input first. Each condition below is independently observable in the returned tuple.
    """
    reasons = []

    # An unapproved bundle is never selected. The reference's PRESENCE is necessary and is not
    # sufficient: it is a pointer at a record the promotion lifecycle owns, and binding reviewer,
    # scope and the exact evaluation hashes to it is that lifecycle's job, not this one's.
    if bundle.provenance["approval_ref"] is None:
        reasons.append("approval-absent")

    for key in _contract().COMPONENT_KEYS:
        pinned = bundle.components[key]
        if pinned is not None and facts["components"].get(key) != pinned:
            reasons.append("component-mismatch")
            break

    if set(bundle.requirements["capabilities"]) - set(facts["capabilities"]):
        reasons.append("capability-unverified")

    if set(bundle.requirements["providers"]) - set(facts["providers"]):
        reasons.append("provider-ineligible")

    required = bundle.requirements["calibration"]
    if required is not None:
        held = facts["calibration"]
        if (held is None or held["id"] != required["id"]
                or held["sha"] != required["sha"]):
            reasons.append("calibration-unmet")

    scope = bundle.scope
    if (facts["project"] != scope["project"]
            or facts["task_class"] not in scope["task_classes"]
            or facts["intended_use"] not in scope["intended_uses"]):
        reasons.append("out-of-scope")

    return tuple(reasons)


def resolve_bundle(pin, bundles, runtime):
    """Which bundle's parameters apply, following fallbacks, ending at legacy.

    `pin` is the reference a run was started under, or None. `bundles` is the catalog of bundle
    payloads available. `runtime` is what the caller can establish about itself, through
    `runtime_facts`.

    This never raises on CONTENT: a malformed bundle, a missing one, a rewritten one and an
    unmet requirement are all outcomes, reported in `reasons`, ending in a resolution that a
    runtime can act on. It does raise on a malformed ARGUMENT -- a catalog that is not a list,
    runtime facts that are not the runtime facts -- because that is a caller defect and
    degrading it to legacy would hide a bug behind a safe-looking answer.
    """
    facts = _runtime(runtime)
    catalog = _catalog(bundles)
    contract = _contract()
    ledger = _al()

    reasons = []
    chain = []

    if pin is None:
        return BundleResolution(source="legacy", bundle=None, ref=None, chain=(),
                                reasons=("no-pin",))
    ref = ledger.read_ref(pin)
    if ref is None or ref["sha"] is None or ref["v"] != contract.BUNDLE_VERSION:
        return BundleResolution(source="legacy", bundle=None, ref=None, chain=(),
                                reasons=("pin-not-a-reference",))

    depth = 0
    seen = set()
    while ref is not None:
        if ref["id"] in seen:
            reasons.append("fallback-cycle")
            break
        if depth > MAX_FALLBACK_DEPTH:
            reasons.append("fallback-depth-exceeded")
            break
        seen.add(ref["id"])
        chain.append(ref["id"])

        payload = catalog.get(ref["id"])
        if payload is None:
            reasons.append("bundle-unknown")
            break
        try:
            bundle = contract.parse_bundle(payload, where=f"bundle[{ref['id']!r}]")
        except contract.ContractError:
            reasons.append("bundle-invalid")
            break
        if not matches_ref(bundle, ref):
            # The content moved under the pointer that named it, so this bundle's OWN fallback
            # pointer was written by whoever moved it. Stop, rather than follow it. The
            # comparison is `matches_ref`'s and not a second spelling of it here, so "does this
            # content still match its pin" has one answer in this module rather than two.
            reasons.append("bundle-content-mismatch")
            break

        unmet = _unmet(bundle, facts)
        if not unmet:
            reasons.append("selected")
            return BundleResolution(
                source="pinned" if depth == 0 else "fallback", bundle=bundle,
                ref=dict(ref), chain=tuple(chain), reasons=tuple(reasons),
            )
        reasons.extend(unmet)

        fallback = bundle.fallback
        if fallback["kind"] == "legacy":
            reasons.append("fallback-legacy")
            ref = None
        else:
            ref = dict(fallback["bundle_ref"])
        depth += 1

    return BundleResolution(source="legacy", bundle=None, ref=None, chain=tuple(chain),
                            reasons=tuple(reasons))


# ---- the historical preference shape ---------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class LegacyPreferenceView:
    """The evaluation workbench's historical preference payload, read for what it is.

    It is pull-only advice about defaults that no driver consumes, and this view does not change
    that. There is no `sha`, no reference and no scope on it, because the payload has none -- and
    there is deliberately no function anywhere that turns one into a `PolicyBundle`. `unmapped`
    is the honest part: the historical shape names its own keys, and this contract does not
    translate them into approved parameters, because translating a preference nobody approved
    into a parameter every run reads is precisely the silent promotion that is refused. Someone
    re-proposes the change through the workbench, with evidence, and it gets reviewed.
    """

    version: str
    policy_version: object
    defaults: types.MappingProxyType
    by_task_class: types.MappingProxyType
    unmapped: tuple
    reasons: tuple


#: Why a preference payload is not a bundle. One code, stable, so a caller can branch on it.
LEGACY_PREFERENCE_REASON = "legacy-preferences-are-not-a-bundle"


def describe_legacy_preferences(payload):
    """Read the historical preference shape. It loads; it does not become a bundle."""
    contract = _contract()
    if not contract.is_legacy_preference_payload(payload):
        raise _refuse("unknown-value",
                      f"this payload is not the {contract.LEGACY_PREFERENCE_VERSION} preference "
                      f"shape; describe_legacy_preferences reads that shape and no other")
    version = payload.get("version")
    if version is not None and (isinstance(version, bool) or not isinstance(version, int)):
        raise _refuse("wrong-type",
                      f"the preference payload's 'version' is {version!r}; it counts applied "
                      f"revisions and is an integer or absent")
    defaults = payload.get("defaults") or {}
    by_class = payload.get("by_task_class") or {}
    for name, value in (("defaults", defaults), ("by_task_class", by_class)):
        if not isinstance(value, dict):
            raise _refuse("wrong-type",
                          f"the preference payload's {name!r} is {type(value).__name__}")
    named = set()
    for key in defaults:
        named.add(key)
    for entry in by_class.values():
        if isinstance(entry, dict):
            named.update(entry)
    unmapped = tuple(sorted(key for key in named if key not in contract.DIFF_PARAMETERS))
    return LegacyPreferenceView(
        version=payload["v"], policy_version=version,
        defaults=types.MappingProxyType(dict(defaults)),
        by_task_class=types.MappingProxyType(
            {key: dict(value) if isinstance(value, dict) else value
             for key, value in by_class.items()}),
        unmapped=unmapped, reasons=(LEGACY_PREFERENCE_REASON,),
    )


# ==============================================================================================
#  D13 -- WHICH ACTION A RUN TAKES, AND WHY IT WAS ENTITLED TO TAKE IT
# ==============================================================================================
# Everything above answers "which parameters are in force". This answers the next question, and
# it is a different concern with its own vocabulary: given the action the EXISTING routing
# already picked, an optional piece of advice about it, and whichever bundle resolved, which
# action does this run actually take, and what is the complete reason?
#
# THE ANSWER, IN EVERY MODE THIS MODULE IMPLEMENTS, IS: THE ONE THE EXISTING ROUTING PICKED.
# `legacy` and `shadow` are the two modes an offline edition exposes. Shadow RECORDS the advice
# and says whether it agreed with the baseline; it does not follow it. Following advice is
# `canary` and `active`, a separately gated runtime transition behind enforcement, evaluation
# and approval evidence this module does not have and does not ask for -- so those two mode
# words are refused BY NAME here rather than quietly treated as a synonym for shadow. Nothing
# in this module reads, locates or consumes a runtime activation pointer; the absence of one is
# the default and needs no code.
#
# WHAT MAKES "A HIGH-CONFIDENCE RESULT NEVER OVERRIDES A HARD DENIAL" STRUCTURAL RATHER THAN A
# PROMISE SOMEBODY HAS TO KEEP. Three things, none of which is a rule to remember:
#
#   1. `_admissible(action, facts)` takes an action label and the coordinator's own facts. There
#      is no parameter through which a result, a probability, a calibrated number or a vendor
#      confidence could arrive, so there is no expression in which one could be weighed against
#      a denial. Nothing anywhere in this module reads an answer's numbers.
#   2. `selected` is never read off the advice. In both modes it is the baseline or it is
#      nothing at all; the advice's ONLY effect on this object is which reason codes it carries.
#   3. The same `_admissible` decides whether the advice was admissible AND why each alternative
#      was set aside, so the two cannot drift into disagreeing about what a denial is.
#
# WHERE THE DENIAL VOCABULARY COMES FROM. `bin/routing_policy.py` already enumerates every way a
# candidate is set aside, in `FILTERS`. Exactly one of them -- `ranked-lower` -- is a PREFERENCE
# outcome rather than a denial: it means another eligible candidate ranked higher, which is
# precisely the kind of choice advice is allowed to have an opinion about. Every other filter is
# a hard denial. `denial_reasons()` derives that split from the router's own tuple instead of
# copying it, so a filter added there is hard here by default, which is the safe direction.
#
# WHICH SEAMS ARE REAL. Derived by reading rather than assumed symmetric. `bin/routing_policy.py`
# has exactly three direct loaders, and they are not three of a kind:
#
#   * `bin/codex_policy.py` routes a task and `bin/codex_execute.py` DISPATCHES under the result.
#     This is the only place in the repository where a routing decision precedes a real dispatch.
#   * `bin/workflow_eval.py` calls `decide` too, but for its own offline comparison of variants;
#     it is the evaluation workbench, not a native driver, and it spends nothing to do it.
#   * `bin/release_gate.py` loads the module only to read a version constant off it.
#
# So there are TWO seam SHAPES in this repository, not four symmetric harness seams:
#
#   * A ROUTING DECISION -- `routing_policy.decide()`'s dict, which is also exactly what
#     `codex_policy.route()` returns. `state_from_routing` wraps it.
#   * A (BASELINE, LADDER) PAIR -- `claude_execute`/`copilot_execute`'s `resolve_model` plus
#     `escalation_ladder`, and Cursor's degenerate case of a baseline with no ladder at all.
#     `state_from_ladder` wraps that.
#
# Neither adapter is wired into a driver, and neither may be: three of the four drivers are
# frozen by D02's goldens against even NAMING `routing_policy`, and consuming a decision at
# dispatch is a later, separately gated task. A green suite says these functions work, never
# that anything calls them.

#: The two modes this module implements. `legacy` is the frozen existing behaviour and the
#: default everywhere. `shadow` additionally records the advice and compares it to the baseline.
#: Neither acts on advice.
SELECTION_MODES = ("legacy", "shadow")

#: The two modes this module deliberately does NOT implement. They are a runtime activation, and
#: a selection that quietly downgraded one of them to shadow would hide the fact that the
#: transition never happened. A test pins `SELECTION_MODES + DEFERRED_MODES` against the
#: contract's own `DECISION_MODES`, so a mode word added there must be classified here.
DEFERRED_MODES = ("canary", "active")

#: The checks only a coordinator can make, and only freshly, immediately before it acts. This
#: module CONSUMES their outcomes and never performs one: it has no registry, no permission
#: system, no project eligibility table and no admission. Each is `True`, `False`, or `None` for
#: "nobody established it" -- and `None` refuses, because an unmade check is not a passed one.
#:
#: The fourth is spelled `budget_admission` and not `budget` on purpose. `budget` is one of the
#: contract's `BANNED_FIELDS`, so that a payload cannot arrive carrying one -- and the OUTCOME of
#: a budget check must not be spelled like the grant itself either. A test sweeps every name this
#: module defines against that ban, which is what keeps the spelling from drifting back.
COORDINATOR_CHECKS = ("capability", "privacy", "eligibility", "budget_admission")

#: The one entry of `routing_policy.FILTERS` that is a ranking rather than a denial.
SOFT_FILTERS = ("ranked-lower",)

#: Why an alternative was set aside when nothing denied it: it simply was not the one selected.
OTHER_REJECTIONS = ("not-selected",)

#: What a selection state must say. Closed, like every other shape here: a fact nobody
#: established is written as an explicit null or an empty collection, never left out.
SELECTION_KEYS = ("request", "baseline", "pin", "reserved", "denials", "checks",
                  "admission_ref")

#: Stable, machine-readable reasons a selection came out the way it did. A SEPARATE vocabulary
#: from `RESOLUTION_REASONS` above and deliberately disjoint from it: resolution answers which
#: parameters are in force, selection answers which action is taken, and a code that meant both
#: would make a report's tally meaningless. A test asserts the two share no member.
SELECTION_REASONS = (
    "action-admission-stale",
    "advice-differs-from-baseline",
    "advice-inadmissible",
    "advice-matches-baseline",
    "baseline-absent",
    "baseline-refused",
    "check-failed",
    "check-unestablished",
    "legacy-default",
    "mode-shadow",
    "no-advice",
    "pin-overridden",
    "recommendation-absent",
    "recommendation-not-an-alternative",
    "result-abstained",
    "result-correlation-mismatch",
    "result-not-answering",
    "result-questions-stale",
    "result-state-stale",
    "shadow-without-bundle",
)
_SELECTION_REASON_SET = frozenset(SELECTION_REASONS)

#: The subset of `SELECTION_REASONS` that REFUSES: a selection carrying one of these selects no
#: action at all. Every other reason is an observation that leaves the baseline standing.
REFUSAL_REASONS = (
    "action-admission-stale",
    "baseline-absent",
    "baseline-refused",
    "check-failed",
    "check-unestablished",
    "pin-overridden",
)
_REFUSAL_SET = frozenset(REFUSAL_REASONS)

#: One sentence per refusal, so a caller can print why without knowing this module's codes. A
#: test pins its keys against `REFUSAL_REASONS`, because a code with no sentence would raise
#: from inside the refusal path -- the one place a raise is least useful.
_REFUSAL_TEXT = {
    "action-admission-stale": ("the grant offered for the action is the one already spent on "
                               "asking; acting needs its own fresh, atomic admission"),
    "baseline-absent": "the existing routing selected no action for this request",
    "baseline-refused": "the action the existing routing selected is denied as things stand now",
    "check-failed": "a fresh coordinator check came back denied",
    "check-unestablished": ("a fresh coordinator check was never made, and an unmade check is "
                            "not a passed one"),
    "pin-overridden": ("the action on offer is not the explicit pin this run was given, and an "
                       "explicit pin is not something a policy may talk its way past"),
}


def _rp():
    """`bin/routing_policy.py`, loaded for its VOCABULARY only.

    This module never calls `decide`, never builds a catalog and never routes. It reads the
    router's contract version, to check that a decision it is handed is one, and the router's
    filter names, so the denial vocabulary has one owner rather than a copy that rots.
    """
    return _sibling("routing_policy")


def denial_reasons():
    """Every `routing_policy` filter that is a HARD denial, derived from the router's own tuple.

    Derived rather than copied, and by SUBTRACTION rather than by listing: a filter added to the
    router lands on the hard side here automatically, which fails closed. Listing the hard ones
    instead would let a new filter fall through as "not a denial" silently.
    """
    return tuple(name for name in _rp().FILTERS if name not in SOFT_FILTERS)


def rejection_reasons():
    """Every reason an alternative may carry for not being the selected one."""
    return tuple(sorted(set(denial_reasons()) | set(OTHER_REJECTIONS)))


# ---- the coordinator's own facts ---------------------------------------------------------------

def _parsed(value, kind, version, where):
    """A first-party object that already went through the contract's parser -- never a payload.

    A dict here would be raw provider data, and the entire point of the contract is that raw
    provider data becomes a judgement only by surviving `parse_request`/`parse_result` first. A
    selection that accepted a payload would be a second, weaker parser for the same bytes.

    Read through `to_payload()` rather than `isinstance`, because `bin/` is not a package and a
    class built by another loader of the same file fails `isinstance` against this one -- the
    defect this kit has already been bitten by. A payload crosses that boundary; a class does
    not.
    """
    if isinstance(value, (dict, types.MappingProxyType)):
        raise _refuse("wrong-type",
                      f"{where} is a payload; run it through the decision contract's own parser "
                      f"first -- a selection reads parsed objects and never raw provider data")
    reader = getattr(value, "to_payload", None)
    if not callable(reader):
        raise _refuse("wrong-type", f"{where} is not a parsed {kind}")
    payload = reader()
    if not isinstance(payload, dict):
        raise _refuse("wrong-type", f"{where} did not read back as a {kind} payload")
    declared = payload.get("v")
    if declared != version:
        raise _refuse("unknown-value",
                      f"{where} declares version {declared!r}; a selection reads {version}")
    return payload


def _checks(value):
    """The four fresh checks, closed, with `None` meaning nobody established it."""
    if not isinstance(value, (dict, types.MappingProxyType)):
        raise _refuse("wrong-type",
                      f"the fresh checks must be an object, got {type(value).__name__}")
    extra = sorted(set(value) - set(COORDINATOR_CHECKS))
    if extra:
        raise _refuse("unknown-field",
                      f"the fresh checks name {', '.join(repr(e) for e in extra)}, which is not "
                      f"a check a coordinator makes")
    missing = sorted(name for name in COORDINATOR_CHECKS if name not in value)
    if missing:
        raise _refuse("missing-field",
                      f"the fresh checks are missing {', '.join(repr(m) for m in missing)}; a "
                      f"check nobody made is written as an explicit null, never left out")
    out = {}
    for name in COORDINATOR_CHECKS:
        outcome = value[name]
        if outcome is not None and not isinstance(outcome, bool):
            raise _refuse("wrong-type",
                          f"the {name!r} check is {outcome!r}; a check passed, failed, or was "
                          f"never made")
        out[name] = outcome
    return out


def _selection(value):
    """The facts a selection is made from, validated and frozen.

    Raises on a CALLER defect -- a state that is not a state, an action that was never an
    eligible alternative, two of the coordinator's own facts contradicting each other. It does
    not degrade any of those to a safe-looking legacy answer, because that would hide a bug
    behind a correct-looking result. What a run can legitimately be in the middle of -- a denied
    baseline, a check that failed, a stale grant -- is an OUTCOME of `select_action`, not a
    refusal here.
    """
    contract = _contract()
    if not isinstance(value, (dict, types.MappingProxyType)):
        raise _refuse("wrong-type",
                      f"the selection state must be an object, got {type(value).__name__}")
    extra = sorted(set(value) - set(SELECTION_KEYS))
    if extra:
        raise _refuse("unknown-field",
                      f"the selection state has unknown field(s) "
                      f"{', '.join(repr(e) for e in extra)}")
    missing = sorted(key for key in SELECTION_KEYS if key not in value)
    if missing:
        raise _refuse("missing-field",
                      f"the selection state is missing {', '.join(repr(m) for m in missing)}")

    # The alternatives come from the REQUEST the provider answered, never from a second list
    # beside it. So a selection cannot name an action that was not on the table when the
    # question was asked, and the record contract's own check on the same field agrees with
    # this one by construction rather than by both being maintained.
    request = _parsed(value["request"], "decision request", contract.CONTRACT_VERSION,
                      "the selection state's 'request'")
    alternatives = tuple(request["alternatives"])
    if not alternatives:
        raise _refuse("value-invalid",
                      "the request names no eligible alternative, so there is nothing to select")

    baseline = value["baseline"]
    if baseline is not None and baseline not in alternatives:
        raise _refuse("unknown-action",
                      f"the baseline is {baseline!r}, which is not one of the eligible "
                      f"alternatives {list(alternatives)}")

    pin = value["pin"]
    if pin is not None and (not isinstance(pin, str) or not pin):
        raise _refuse("value-invalid",
                      "an explicit pin is a non-empty action name, or null for no pin")

    held = value["reserved"]
    if not isinstance(held, (list, tuple)):
        raise _refuse("wrong-type", "the reserved defaults must be a list")
    for item in held:
        if item not in alternatives:
            raise _refuse("unknown-action",
                          f"{item!r} is held back as a reserved default but was never an "
                          f"eligible alternative")
    held = tuple(dict.fromkeys(held))

    denials = value["denials"]
    if not isinstance(denials, (dict, types.MappingProxyType)):
        raise _refuse("wrong-type", "the denials must be an object of action -> reason")
    permitted = set(denial_reasons())
    for action, reason in denials.items():
        if action not in alternatives:
            raise _refuse("unknown-action",
                          f"{action!r} is denied but was never an eligible alternative")
        if reason not in permitted:
            raise _refuse("unknown-value",
                          f"{action!r} is denied for {reason!r}; the denial vocabulary is the "
                          f"router's own: {', '.join(permitted)}")
    both = sorted(set(held) & set(denials))
    if both:
        # Held back and denied are different facts with different remedies, and an action
        # carrying both would let whichever check ran first mask the other one forever.
        raise _refuse("duplicate-entry",
                      f"{', '.join(repr(b) for b in both)} is both held back as a reserved "
                      f"default and denied; these are different facts and an action has one")
    if baseline is not None and baseline in held:
        raise _refuse("value-invalid",
                      f"the baseline {baseline!r} is also held back as a reserved default; "
                      f"these two facts come from the same coordinator and disagree")

    admission = _al().read_ref(value["admission_ref"])
    if admission is None:
        raise _refuse("not-a-reference",
                      "the selection state's 'admission_ref' is not a reference; acting needs a "
                      "fresh grant and there is no null that means 'acting anyway'")

    return types.MappingProxyType({
        "request": request,
        "alternatives": alternatives,
        "baseline": baseline,
        "pin": pin,
        "reserved": held,
        "denials": dict(denials),
        "checks": _checks(value["checks"]),
        "admission_ref": dict(admission),
    })


def selection_state(*, request, baseline, checks, admission_ref, pin=None, reserved=(),
                    denials=None):
    """A selection state from named arguments, refused at the seam rather than three calls on.

    The copies below are taken AFTER validation and from the validated facts, never before and
    never from the caller's own objects. Taking them first is the near-miss this function
    already made once: `dict(denials)` on a list and `list(reserved)` on a string both succeed
    or crash with a bare `ValueError`, so the coercion answered the question before the contract
    could -- one of them silently turning a model id into a list of its letters.
    """
    state = {
        "request": request, "baseline": baseline, "pin": pin, "reserved": reserved,
        "denials": {} if denials is None else denials, "checks": checks,
        "admission_ref": admission_ref,
    }
    facts = _selection(state)
    state["reserved"] = list(facts["reserved"])
    state["denials"] = dict(facts["denials"])
    state["checks"] = dict(facts["checks"])
    return state


# ---- what a selection is -----------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class ActionSelection:
    """Which action this run takes, which advice it had, and the whole reason for both.

    `BundleResolution` above deliberately carries no mode, because resolving a bundle grants
    nothing. THIS object carries one, and the difference is the point: a mode is a fact about
    how the coordinator is running, established by the coordinator, and recorded here so the
    decision record can say it. It is still not a grant -- `selected` is the baseline or it is
    nothing, in both modes.

    `recommended` IS NOT the field a `DecisionRecord` carries under that name, and the two are
    different on purpose. The record reports what the provider said, always, because reporting
    the advice it got is the record's job -- and `build_record` copies that field out of the
    result itself, so no caller can get it from here by mistake. This field is narrower: the
    advice the selection was ENTITLED to consider, which is null when the result answered a
    different world, answered nothing, or named something that was never on the table.
    """

    mode: str
    requested_mode: str
    baseline: object
    recommended: object
    recommendation: object
    selected: object
    refusal: object
    bundle_sha: object
    reasons: tuple
    rejected: tuple

    def __post_init__(self):
        contract = _contract()
        for field, value in (("mode", self.mode), ("requested_mode", self.requested_mode)):
            if value not in SELECTION_MODES:
                raise _refuse("unknown-value",
                              f"a selection's {field} is {value!r}; the modes this module "
                              f"implements are {', '.join(SELECTION_MODES)}")
        undeclared = sorted(set(self.reasons) - _SELECTION_REASON_SET)
        if undeclared:
            raise _refuse("unknown-value",
                          f"a selection carries undeclared reason(s) "
                          f"{', '.join(repr(u) for u in undeclared)}")
        if len(set(self.reasons)) != len(self.reasons):
            raise _refuse("duplicate-entry", "a selection repeats a reason code")
        if not self.reasons or len(self.reasons) > contract.MAX_REASON_CODES:
            raise _refuse("bounds-exceeded",
                          f"a selection carries {len(self.reasons)} reason(s); a record holds "
                          f"between 1 and {contract.MAX_REASON_CODES}")
        # An action was selected exactly when nothing refused, and a refusal always names a
        # DECLARED cause. Without the second half a selection could refuse for a reason nobody
        # can count, which is the same defect as an undeclared reason code with extra steps.
        if (self.selected is None) != (self.refusal is not None):
            raise _refuse("value-invalid",
                          "a selection names an action exactly when nothing refused it; the "
                          "selected action and the refusal disagree")
        refusing = sorted(set(self.reasons) & _REFUSAL_SET)
        if (self.selected is None) != bool(refusing):
            raise _refuse("value-invalid",
                          f"a selection refuses exactly when it carries a refusal reason; this "
                          f"one selected {self.selected!r} while carrying {refusing}")
        # Shadow cannot exist without a bundle in force: shadow IS the comparison a bundle's
        # parameters are being compared against, and a shadow over nothing is just legacy
        # wearing the other word.
        if self.mode == "shadow" and self.bundle_sha is None:
            raise _refuse("value-invalid",
                          "a shadow selection reports the digest of the bundle in force; there "
                          "is no shadow without one")
        permitted = set(rejection_reasons())
        seen = set()
        for entry in self.rejected:
            action = entry["action"]
            if action == self.selected:
                raise _refuse("value-invalid",
                              f"a selection lists its own selected action {action!r} as rejected")
            if action in seen:
                raise _refuse("duplicate-entry", f"a selection rejects {action!r} twice")
            seen.add(action)
            if entry["reason"] not in permitted:
                raise _refuse("unknown-value",
                              f"{action!r} was rejected for {entry['reason']!r}, which is not a "
                              f"declared rejection reason")

    def reason(self, code):
        return code in self.reasons


def _mode(value):
    """The mode this selection runs in, or a refusal naming what is missing."""
    if value in DEFERRED_MODES:
        raise _refuse("unknown-value",
                      f"mode {value!r} is a runtime activation, which this module cannot perform "
                      f"and must not approximate: it is a separately gated transition behind "
                      f"enforcement, evaluation and approval evidence that lives elsewhere. The "
                      f"modes implemented here are {', '.join(SELECTION_MODES)}")
    if value not in SELECTION_MODES:
        raise _refuse("unknown-value",
                      f"a selection's mode is {value!r}; the vocabulary is "
                      f"{', '.join(SELECTION_MODES)}")
    return value


def _in_force(bundle):
    """`(resolution source, bundle digest)` for a resolved bundle, or `(None, None)` for legacy.

    Duck-typed across the loader boundary for the reason stated at the top of this file. Legacy
    reads exactly like no bundle at all, which is what legacy IS.
    """
    if bundle is None:
        return None, None
    source = getattr(bundle, "source", None)
    if source not in RESOLUTION_SOURCES:
        raise _refuse("wrong-type",
                      "select_action takes a bundle resolution or None; this is neither")
    if source == "legacy":
        return None, None
    resolved = getattr(bundle, "bundle", None)
    digest = getattr(resolved, "sha", None)
    if not callable(digest):
        raise _refuse("wrong-type",
                      f"a {source!r} resolution carries no bundle to take a digest of")
    return source, digest()


def _admissible(action, facts):
    """Why `action` cannot be acted on as things stand, or None when nothing stands in its way.

    THE SIGNATURE IS THE GUARANTEE. There is no parameter here through which a result, a
    probability, a calibrated number or a vendor's confidence could arrive, so there is no
    expression in this function that could weigh one against a denial. A maximally confident
    recommendation and an abstention reach this function as the same thing: a name.

    One function, three callers -- the baseline, the advice, and every rejected alternative --
    so what counts as a denial cannot come out differently depending on who asked.
    """
    denied = facts["denials"].get(action)
    if denied is not None:
        return denied
    if action in facts["reserved"]:
        return "reserved"
    if facts["pin"] is not None and action != facts["pin"]:
        return "pinned-elsewhere"
    return None


def _advice(facts, result):
    """The advice this selection may consider -> `(action or None, reason codes)`.

    Every check that can fail independently is collected rather than short-circuited, for the
    reason `_unmet` above gives: a caller told only the first thing wrong comes back for the
    next one, and a test asserting one specific reason cannot be satisfied by a different check
    refusing the same input first.
    """
    contract = _contract()
    codes = []
    if result is None:
        codes.append("no-advice")
        return None, codes

    payload = _parsed(result, "decision result", contract.CONTRACT_VERSION, "the result")
    request = facts["request"]
    stale = False
    if payload["correlation_id"] != request["correlation_id"]:
        codes.append("result-correlation-mismatch")
        stale = True
    if payload["state_sha"] != request["state_sha"]:
        codes.append("result-state-stale")
        stale = True
    if payload["questions_sha"] != request["questions_sha"]:
        codes.append("result-questions-stale")
        stale = True
    if stale:
        # Advice about a different world is not weak advice, it is advice about a different
        # world. It is dropped whole; the run continues on the baseline, which is the approved
        # fallback and needed no advice to begin with.
        return None, codes

    status = payload["status"]
    if status == "abstain":
        # An abstention is the ABSENCE of a judgement. Reading one as agreement with the
        # baseline would turn "I have nothing to say" into a second vote for whatever was
        # already happening, and reading it as a recommendation would be worse.
        codes.append("result-abstained")
        return None, codes
    if status not in contract.ANSWERING_STATUSES:
        codes.append("result-not-answering")
        return None, codes

    advised = payload["recommended"]
    if advised is None:
        codes.append("recommendation-absent")
        return None, codes
    if advised not in facts["alternatives"]:
        # Reachable with two genuinely parsed objects: correlation, state and question digests
        # can all agree while the alternatives differ, because the alternatives are inside
        # `request.sha()` and none of those three.
        codes.append("recommendation-not-an-alternative")
        return None, codes
    return advised, codes


def select_action(state, result=None, bundle=None, *, mode="legacy"):
    """Which action this run takes, and the complete reason -> an `ActionSelection`.

    PURE, and pure in the strong sense: it dispatches nothing, opens nothing, writes nothing,
    starts nothing and asks nothing of a provider. It reports what it would select and why. The
    coordinator performs the checks, holds the grant, takes the action and writes the record;
    this says what the record should say.

    `state` is a selection state (`selection_state`, or one of the two seam adapters below).
    `result` is a PARSED `DecisionResult` or None. `bundle` is a `BundleResolution` or None.
    `mode` is `legacy` (the default, and the existing behaviour) or `shadow`.

    In both modes the selected action is the baseline or nothing. That is not a placeholder for
    a smarter rule later: it is the entire safety property this task exists to hold, and the
    rule that replaces it is a gated runtime transition with its own evidence.
    """
    requested = _mode(mode)
    facts = _selection(state)
    codes = []

    source, bundle_sha = _in_force(bundle)
    effective = requested
    if requested == "shadow" and source is None:
        # Asking for shadow with nothing in force restores legacy rather than pretending. This
        # is the "disabled restores" direction: take the bundle away and the behaviour is the
        # behaviour that was there before any of this existed.
        effective = "legacy"
        codes.append("shadow-without-bundle")
    if effective == "legacy":
        codes.append("legacy-default")
    else:
        codes.append("mode-shadow")

    # ---- the fresh checks, all of them, never short-circuited ----
    refused = []
    if any(facts["checks"][name] is False for name in COORDINATOR_CHECKS):
        refused.append("check-failed")
    if any(facts["checks"][name] is None for name in COORDINATOR_CHECKS):
        refused.append("check-unestablished")
    if facts["admission_ref"]["id"] == facts["request"]["admission_ref"]["id"]:
        # The same refusal `parse_record` makes, made before the action rather than after it:
        # the grant that admitted ASKING is already spent, and acting is a second operation.
        refused.append("action-admission-stale")

    baseline = facts["baseline"]
    if baseline is None:
        refused.append("baseline-absent")
    else:
        blocked = _admissible(baseline, facts)
        if blocked == "pinned-elsewhere":
            # Named for what it is rather than folded into the generic refusal, so the one case
            # that means "somebody overrode an explicit pin" is countable on its own.
            refused.append("pin-overridden")
        elif blocked is not None:
            refused.append("baseline-refused")
    codes.extend(refused)

    selected = None if refused else baseline
    refusal = None
    if selected is None:
        refusal = "; ".join(_REFUSAL_TEXT[code] for code in refused)

    # ---- the advice, recorded in both modes and followed in neither ----
    advised, advice_codes = _advice(facts, result)
    codes.extend(advice_codes)
    recommendation = None
    if advised is not None:
        blocked = _admissible(advised, facts)
        recommendation = types.MappingProxyType(
            {"action": advised, "admissible": blocked is None, "reason": blocked})
        if blocked is not None:
            codes.append("advice-inadmissible")
        elif advised == baseline:
            codes.append("advice-matches-baseline")
        else:
            codes.append("advice-differs-from-baseline")

    # ---- every alternative that was not selected, and why it could not have been ----
    entries = []
    for action in facts["alternatives"]:
        if action == selected:
            continue
        reason = _admissible(action, facts)
        entries.append(types.MappingProxyType(
            {"action": action, "reason": OTHER_REJECTIONS[0] if reason is None else reason}))

    return ActionSelection(
        mode=effective, requested_mode=requested, baseline=baseline, recommended=advised,
        recommendation=recommendation, selected=selected, refusal=refusal,
        bundle_sha=bundle_sha, reasons=tuple(codes), rejected=tuple(entries),
    )


# ---- the two selection seams this repository actually has ---------------------------------------
#
# Derived by reading rather than assumed symmetric. `bin/routing_policy.py` has three direct
# loaders and only one of them dispatches under a routing decision, so the seams are:
#
#   1. A ROUTING DECISION. `routing_policy.decide()` returns it and `codex_policy.route()`
#      returns exactly the same dict with an `assignment` key added, so ONE adapter covers both
#      and the Codex driver, which is the only driver that dispatches under one.
#   2. A (BASELINE, LADDER) PAIR. `claude_execute` and `copilot_execute` resolve a model and
#      build an escalation ladder from their own pricing files and never touch the router;
#      `cursor_execute` has no ladder at all, which is this seam with an empty one.
#
# NOTHING CALLS EITHER OF THESE. They are adapters offered to a later, separately gated task,
# and three of the four drivers are frozen by their own goldens against even naming the router.

def state_from_routing(decision, *, request, checks, admission_ref):
    """A selection state from a routing decision. Wraps the router; never re-decides.

    Reads the decision as data: the model it picked is the baseline, `floor.pinned` is the
    explicit pin, and each candidate's own recorded filter is the denial. No rule here rederives
    any of that, because a second implementation of the router's own decision is exactly the
    duplicate authority this repository forbids -- and one that disagreed would be worse than
    one that was simply absent.

    A candidate held back as the reserved orchestrator lands in `reserved` and NOT in `denials`,
    even though `reserved` is spelled the same in both vocabularies: an action carries one fact,
    and carrying both would let whichever check ran first mask the other permanently.

    Candidates the request never listed as eligible alternatives are skipped rather than
    refused. The router's catalog includes rows that were never on the table -- non-routable
    models, cost-only entries -- precisely so an explanation can name them.
    """
    router = _rp()
    if not isinstance(decision, dict):
        raise _refuse("wrong-type",
                      f"a routing decision is an object, got {type(decision).__name__}")
    declared = decision.get("v")
    if declared != router.CONTRACT_VERSION:
        raise _refuse("unknown-value",
                      f"this payload declares {declared!r}; state_from_routing reads "
                      f"{router.CONTRACT_VERSION} decisions and no other shape")
    alternatives = tuple(_parsed(request, "decision request", _contract().CONTRACT_VERSION,
                                 "the request")["alternatives"])
    hard = set(denial_reasons())
    held = []
    denials = {}
    for entry in decision.get("candidates") or ():
        if not isinstance(entry, dict):
            raise _refuse("wrong-type", "a routing decision's candidates are objects")
        identity = entry.get("id")
        if identity not in alternatives:
            continue
        # The router's filter chain records at most one hard filter per candidate; a further
        # `ranked-lower` is a ranking and never a denial. Taking the first hard one is therefore
        # exact rather than a choice between competing reasons.
        blocking = [name for name in (entry.get("reasons") or ()) if name in hard]
        if not blocking:
            continue
        if blocking[0] == "reserved":
            held.append(identity)
        else:
            denials[identity] = blocking[0]
    floor = decision.get("floor") or {}
    return selection_state(request=request, baseline=decision.get("model"),
                           pin=floor.get("pinned"), reserved=held, denials=denials,
                           checks=checks, admission_ref=admission_ref)


def state_from_ladder(*, request, baseline, ladder, checks, admission_ref, pin=None,
                      reserved=(), denials=None):
    """A selection state from a driver's own `(baseline, escalation ladder)` pair.

    This is a THIN adapter and saying so is more useful than dressing it up: the drivers that
    use this shape resolve a model and a ladder from their own pricing file, and the only thing
    this adds is the coherence check that every rung was an eligible alternative of the request
    the provider answered. That check is the whole point of having a seam -- it is where a rung
    that was never on the table would otherwise enter the decision unnoticed.

    The ladder is not an ordering this selection uses. Nothing here climbs it: a rung is reached
    after an attempt fails, and no attempt has failed at selection time.
    """
    alternatives = tuple(_parsed(request, "decision request", _contract().CONTRACT_VERSION,
                                 "the request")["alternatives"])
    if not isinstance(ladder, (list, tuple)):
        raise _refuse("wrong-type", f"a ladder is a list, got {type(ladder).__name__}")
    for rung in ladder:
        if rung not in alternatives:
            raise _refuse("unknown-action",
                          f"the ladder offers {rung!r}, which the request never listed as an "
                          f"eligible alternative")
    if baseline is not None and baseline in ladder:
        raise _refuse("duplicate-entry",
                      f"the baseline {baseline!r} is also a rung of the ladder above it")
    return selection_state(request=request, baseline=baseline, pin=pin, reserved=reserved,
                           denials=denials, checks=checks, admission_ref=admission_ref)


# ==============================================================================================
#  D17 -- WHETHER ONE BOUNDED CONTEXT REPAIR IS ADMISSIBLE, AND WHY IT IS OFF UNTIL IT IS
# ==============================================================================================
# The recovery experiment's arm C supplies "one bounded package of previously missing contract
# context" before a SAME-MODEL retry, and then returns to the recovery path the driver already
# had. `bin/decision_context.py` builds that package's manifest. This answers the question
# before it: given a failure the ledger already classified, a manifest already built, and the
# bundle already resolved above, is ONE such repair admissible at all -- and if not, exactly
# which of the sixteen things that must be true is not.
#
# IT PLANS. IT DOES NOT REPAIR, RETRY, DISPATCH, WRITE OR ACTIVATE ANYTHING.
# Like every other function in this file it is pure: no file, no process, no store, no clock.
# `plan_context_repair` returns a description of an operation a coordinator MIGHT perform. It
# performs none of it, and there is no coordinator: nothing in this repository calls it.
#
# ============================================================================================
#  WHY "OFF BY DEFAULT" IS NOT A FLAG HERE
# ============================================================================================
# A boolean argument defaulting to False is off until somebody passes True, which is one typo,
# one copied call site or one enthusiastic wrapper away from on. There is no such argument.
# THE ONLY THING THAT CAN PUT A CONTEXT REPAIR IN FORCE IS A RESOLVED POLICY BUNDLE whose own
# data parameters say so -- `REPAIR_PARAMETER`, which is one of the contract's four allowlisted
# `DIFF_PARAMETERS` and is `boolean` there. To hold one of those a caller must have come through
# `resolve_bundle` above with a pin naming a bundle that is in the catalog, parses, digests to
# what the pin said, carries an approval reference, is in scope for this project/task
# class/intended use, pins component versions the runtime actually runs, and requires no
# capability the registry has not VERIFIED. Every one of those is a refusal in
# `RESOLUTION_REASONS`, and every one of them ends at legacy -- and legacy, which is what a run
# with no pin gets, sets no parameters at all and therefore can never put a repair in force.
#
# Two more things follow from that and are worth saying out loud. Resolving such a bundle still
# does not ACTIVATE anything: `select_action` above continues to select the baseline in both
# modes this module implements, and a plan produced here is an input to a coordinator's fresh
# checks, never a substitute for one. And `plan_context_repair` has NO parameter with a default
# value, of any kind -- a caller supplies every fact or the call does not run -- so there is no
# argument a caller can forget in the permissive direction.
#
# ============================================================================================
#  WHAT A "GENUINE IMPLEMENTATION FAILURE" IS, AND WHY IT IS READ AND NEVER GUESSED
# ============================================================================================
# `tasks/kits/decision-improvement/PLAN.md`: "Infrastructure/auth/permission/unavailable-model
# failures are determined from trusted events and never trigger model escalation by a semantic
# guess." The same rule governs a context repair, and more strictly, because supplying a package
# of interfaces to a run that could not authenticate spends a dispatch on a diagnosis nobody
# made.
#
# So the trigger is `attempt_history`'s own projected `failure_class`, written by
# `attempt_ledger.classify_dispatch` from the process runner's observation and the dispatch's
# own exit status, and read here from the record and from nowhere else. Exactly one class
# qualifies -- `verification`, the deterministic check failing on work the model actually
# produced. `auth`, `config` (which is where an unknown or unavailable model lands),
# `permission` and `infrastructure` are facts about the host. `model` is the model's own
# failure, whose remedy is the ladder's, and changing model and context at once is the one
# thing the experiment's design forbids. `unknown` is a non-zero exit nobody could attribute,
# and an unattributed failure is not a free retry.
#
# A second, independent fact has to agree: the record's own `verify_rc`. A record claiming a
# verification failure whose deterministic check exited 0 contradicts itself, and a record that
# never recorded an exit status never observed the failure at all.
#
# ============================================================================================
#  THE LADDER IS CARRIED, FROZEN, AND NEVER CLIMBED
# ============================================================================================
# A repair is ONE retry on the SAME model, and what happens after it is whatever the driver's
# own escalation ladder already said. This module copies that ladder onto the plan verbatim --
# same rungs, same order, nothing added, nothing consumed -- so the thing a coordinator returns
# to is the thing it already had. It is carried rather than merely omitted because a plan that
# did not say where the run goes next would read as though the repair were the end of the path.
#
# ============================================================================================
#  WHAT WOULD STILL HAVE TO BE TRUE BEFORE ONE COULD ACTUALLY RUN
# ============================================================================================
# All of this is offline. For a context repair to happen to anyone: something would have to CALL
# this function (nothing does); an approved `PolicyBundle` carrying `REPAIR_PARAMETER` would
# have to exist and be pinned (none does); a kit would have to declare every budget ceiling the
# operation draws down (none in this repository declares any); a coordinator would have to mint
# a second admission grant for the repair and then actually dispatch under it (no dispatch path
# consumes a plan). This task builds none of those and authorises none of them.

#: The bundle data parameter that puts a context repair in force, and the one that bounds how
#: much context it may carry. Both are keys of the contract's `DIFF_PARAMETERS` allowlist --
#: `boolean` and `count` respectively -- and a test pins them there, so this module cannot
#: invent a dial the contract would refuse on a bundle or in a proposal's diff.
REPAIR_PARAMETER = "recovery.contract_context_package"
REPAIR_FILES_PARAMETER = "recovery.contract_context_files"

#: The consuming operation a repair IS. Not a new word: it is a key of
#: `kit_contract.OPERATION_CAPS`, so a repair draws down exactly the ceilings a retry has always
#: drawn down and `max-dispatches` keeps the meaning every recorded ledger already gave it. A
#: repair is a retry that was handed a package, not a fifth kind of operation beside them.
REPAIR_OPERATION = "retry"

#: The one failure class a context repair answers. Everything else the ledger can determine is
#: a fact about the host, the model, or nobody's knowledge -- see the header.
REPAIRABLE_FAILURE_CLASSES = ("verification",)

#: Stable, machine-readable reasons a repair plan came out the way it did. A THIRD vocabulary,
#: deliberately disjoint from `RESOLUTION_REASONS` (which parameters are in force) and from
#: `SELECTION_REASONS` (which action is taken). This answers a different question again --
#: whether one bounded extra operation is admissible -- and a code that meant two of the three
#: would make all three reports' tallies meaningless. A test asserts the three share no member.
REPAIR_REASONS = (
    "acceptance-unidentified",
    "admission-not-separate",
    "assurance-undeclared",
    "checkpoint-moved",
    "checkpoint-unidentified",
    "context-absent",
    "context-bound-undeclared",
    "context-over-bound",
    "dispatch-cap-reached",
    "dispatch-cap-undeclared",
    "failure-class-excluded",
    "failure-class-unestablished",
    "failure-not-observed",
    "model-unidentified",
    "repair-admissible",
    "repair-already-taken",
    "repair-not-in-force",
)
_REPAIR_REASON_SET = frozenset(REPAIR_REASONS)

#: The single code that is NOT a refusal. Every other member of the vocabulary above says why
#: no repair is admissible, and a plan carries either this one alone or some of the others.
REPAIR_ADMISSIBLE = "repair-admissible"

#: One sentence per refusal, so a caller can print why without knowing this module's codes. A
#: test pins its keys against the refusal set, for the reason D13 already found: a code with no
#: sentence raises from inside the refusal path, which is the one place a raise helps least.
_REPAIR_TEXT = {
    "acceptance-unidentified": ("the failed attempt recorded no acceptance reference, and "
                                "criteria that cannot be named cannot be preserved"),
    "admission-not-separate": ("a repair is its own admitted operation and needs its own fresh "
                               "grant; this one is the grant the failed attempt already spent, "
                               "or the failed attempt recorded no grant to be separate from"),
    "assurance-undeclared": ("the run declared no assurance for this repair to carry forward, "
                             "and a retry that drops an independent check is a different "
                             "operation from the one that failed"),
    "checkpoint-moved": ("the context package was assembled over a different revision than the "
                         "one the retry would run at; it is not this checkpoint's missing "
                         "context"),
    "checkpoint-unidentified": ("nobody could say which revision the retry would run at, so "
                                "there is no failing checkpoint to restore the package against"),
    "context-absent": ("the manifest found no applicable context, which is a legitimate "
                       "abstention: there is no package to supply and a retry without one is "
                       "the ladder's business"),
    "context-bound-undeclared": ("the bundle that puts the repair in force declares no ceiling "
                                 "on how many files the package may carry, and a bounded "
                                 "package with no declared bound is not bounded"),
    "context-over-bound": ("the manifest carries more candidates than the bundle in force "
                           "permits this package to supply"),
    "dispatch-cap-reached": ("a ceiling this operation draws down is already reached, and a "
                             "repair spends inside the existing ceilings rather than beside "
                             "them"),
    "dispatch-cap-undeclared": ("the run declares no ceiling for a ceiling this operation draws "
                                "down; an extra attempt nobody is counting is exactly the "
                                "unbounded retry this refuses to be"),
    "failure-class-excluded": ("the ledger classified this failure as the host's, the model's "
                               "own, or nobody's knowledge; a package of interfaces answers "
                               "none of those and spending a dispatch on one is a guess"),
    "failure-class-unestablished": ("nothing classified this failure, and an unclassified "
                                    "failure is not a classified-as-repairable one"),
    "failure-not-observed": ("the deterministic check's own exit status does not show a "
                             "failure, so there is nothing here to repair"),
    "model-unidentified": ("the failed attempt recorded no dispatched model, and a repair that "
                           "cannot preserve the model would change model and context at once"),
    "repair-already-taken": ("a context repair was already admitted for this task; at most one "
                             "is permitted and the rest of the recovery path is the ladder's"),
    "repair-not-in-force": ("no resolved policy bundle puts a context repair in force. This is "
                            "the default everywhere and the only way out of it is an approved "
                            "bundle whose own data parameters say otherwise"),
}


def _kc():
    """`bin/kit_contract.py`, loaded for the OPERATION AND BUDGET VOCABULARY it already owns.

    This module defines no operation kind, no budget key and no assurance word of its own. It
    reads the ones the task contract already declares, so a cap added there is a cap here and a
    role whose assurance kind is new is accepted without an edit to this file.
    """
    return _sibling("kit_contract")


def _ah():
    """`bin/attempt_history.py`, loaded for the FIELD NAMES of the projection it reads."""
    return _sibling("attempt_history")


def _dx():
    """`bin/decision_context.py`, the context-candidate seam D16 owns.

    Read for its manifest version, its status vocabulary, its reference builder and its
    dependency-claim sweep. This module never builds a manifest -- building one opens files, and
    this module opens nothing.
    """
    return _sibling("decision_context")


def assurance_kinds():
    """Every assurance kind the task contract declares, derived from its own tables.

    By UNION rather than by a list kept here, for the reason `denial_reasons()` is by
    subtraction: a role added to `kit_contract.ROLE_CONTRACTS` with a new assurance kind is
    accepted automatically, and nothing in this file has to be remembered.
    """
    contract = _kc()
    kinds = set()
    for entry in contract.WORKFLOW_ASSURANCE.values():
        kinds.update(entry)
    for role in contract.ROLE_CONTRACTS.values():
        if role["assurance"]:
            kinds.add(role["assurance"])
    return tuple(sorted(kinds))


def _no_dependency_claim(value, where):
    """D16's own sweep, re-raised in THIS loader's exception class.

    `bin/` is not a package, so `decision_context`'s refusal is built by ITS instance of the
    contract, and a caller catching this module's `ContractError` would miss it entirely -- the
    loader defect this file's header names. Both classes derive from `ValueError`, which is what
    makes the catch work across the boundary, and the code rides on the object. Anything that is
    not that refusal propagates untouched: relabelling an unrelated `ValueError` as an authority
    field would be inventing a diagnosis.
    """
    try:
        _dx().assert_no_dependency_claim(value, where)
    except ValueError as error:
        if getattr(error, "code", None) != "authority-field":
            raise
        raise _refuse("authority-field", str(error).split("] ", 1)[-1]) from error
    return value


def _failed_attempt(record):
    """The authoritative failure event, checked against `attempt_history`'s OWN field names.

    A shape assembled beside that projection is not the projection. Every fact a repair is
    planned on -- the failure class, the deterministic check's exit status, the model that was
    dispatched, the acceptance the attempt ran against, the grant that funded it -- is read from
    here and from nowhere else, so nothing in this module can determine a failure by reading
    output text and guessing.
    """
    if not isinstance(record, (dict, types.MappingProxyType)):
        raise _refuse("wrong-type",
                      f"the failed attempt must be an attempt history record, got "
                      f"{type(record).__name__}")
    fields = set(_ah().RECORD_FIELDS)
    extra = sorted(set(record) - fields)
    if extra:
        raise _refuse("unknown-field",
                      f"the failed attempt carries {', '.join(repr(e) for e in extra)}, which "
                      f"bin/attempt_history.py does not project; a repair reads that projection "
                      f"and not a shape assembled beside it")
    for name in ("task", "failure_class", "verify_rc"):
        if name not in record:
            raise _refuse("missing-field",
                          f"the failed attempt records no {name!r}; an absent field and a null "
                          f"one are different facts and only one of them is honest here")
    return record


def _manifest(value):
    """A D16 context-candidate manifest, read for its status, its bounds and its candidates."""
    context = _dx()
    if not isinstance(value, dict):
        raise _refuse("wrong-type",
                      f"the context manifest must be an object, got {type(value).__name__}")
    if value.get("v") != context.CONTEXT_VERSION:
        raise _refuse("unknown-value",
                      f"the context manifest declares {value.get('v')!r}; a repair reads "
                      f"{context.CONTEXT_VERSION} manifests and no other shape")
    if value.get("status") not in context.MANIFEST_STATUSES:
        raise _refuse("unknown-value",
                      f"the context manifest's status is {value.get('status')!r}; the "
                      f"vocabulary is {', '.join(context.MANIFEST_STATUSES)}")
    rows = value.get("candidates")
    if not isinstance(rows, list):
        raise _refuse("wrong-type", "the context manifest's 'candidates' must be a list")
    return value


def _repair_in_force(bundle):
    """`(in force, bundle digest, file bound)` for the resolved bundle -- the WHOLE off switch.

    Legacy and no bundle at all read identically and both mean off, which is what off IS: the
    behaviour a run has before any of this exists. A bundle in force says so through the
    contract's own allowlisted parameter, compared with `is True` rather than for truthiness,
    because a repair that could be switched on by any value that happens to be truthy is a
    repair switched on by accident.
    """
    source, digest = _in_force(bundle)
    if source is None:
        return False, None, None
    parameters = getattr(bundle, "parameters", None)
    if not isinstance(parameters, (dict, types.MappingProxyType)):
        raise _refuse("wrong-type",
                      f"a {source!r} resolution carries no parameters to read a repair from")
    if parameters.get(REPAIR_PARAMETER) is not True:
        return False, digest, None
    return True, digest, parameters.get(REPAIR_FILES_PARAMETER)


def _budget(plan_budget, used):
    """The kit's declared ceilings and what they have already spent, validated, never raised."""
    contract = _kc()
    out = {}
    for name, value in (("budget", plan_budget), ("used", used)):
        if not isinstance(value, (dict, types.MappingProxyType)):
            raise _refuse("wrong-type",
                          f"the declared {name} must be an object, got {type(value).__name__}")
        unknown = sorted(set(value) - set(contract.PLAN_BUDGET_KEYS))
        if unknown:
            raise _refuse("unknown-field",
                          f"the declared {name} names {', '.join(repr(u) for u in unknown)}, "
                          f"which is not a ceiling the task contract declares")
        cleaned = {}
        for key, entry in value.items():
            if isinstance(entry, bool) or not isinstance(entry, int) or entry < 0:
                raise _refuse("value-invalid",
                              f"the declared {name}'s {key!r} is {entry!r}; a ceiling and a "
                              f"count are non-negative integers")
            cleaned[key] = entry
        out[name] = cleaned
    return out["budget"], out["used"]


def _strings(value, what, *, ceiling=64):
    """A bounded tuple of non-empty strings, refused rather than coerced.

    Uncoerced on purpose: `list("fake-model")` is a list of ten letters and `dict(some_list)`
    raises a bare `ValueError`, and either would answer the question before the contract could.
    That defect has now been found twice in this file, once in each half.
    """
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise _refuse("wrong-type", f"{what} must be a list of names, got "
                                    f"{type(value).__name__}")
    if len(value) > ceiling:
        raise _refuse("bounds-exceeded",
                      f"{what} carries {len(value)} entries; the ceiling is {ceiling}")
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise _refuse("value-invalid", f"{what} carries {item!r}; each entry is a name")
    return tuple(value)


def _prior_repairs(value):
    """Repair identities a coordinator has already recorded for this task.

    Each is one of the content digests this module mints below, so a caller cannot satisfy the
    duplicate check with a placeholder. What this CANNOT do is find a repair nobody recorded:
    the guard is exactly as good as the record-keeping of whoever calls it, and today nothing
    does.
    """
    entries = _strings(value, "the prior repairs", ceiling=16)
    for item in entries:
        if len(item) != 64 or any(ch not in "0123456789abcdef" for ch in item):
            raise _refuse("value-invalid",
                          f"{item!r} is not a repair identity; a repair is named by the digest "
                          f"this module mints for it")
    return entries


@dataclasses.dataclass(frozen=True)
class ContextRepair:
    """Whether one bounded context repair is admissible, and the whole reason either way.

    `admissible` is the module's existing word (`ActionSelection.recommendation` already uses
    it) and it is deliberately not `admitted`: NOTHING HERE ADMITS ANYTHING. A budget grant
    admits an operation, a coordinator performs its fresh checks and takes it, and this object
    reports that every precondition a pure function can check is satisfied. It is an input to
    that decision and never a substitute for one.

    `ladder` is the driver's own remaining recovery path, carried verbatim in both outcomes, so
    the plan always says where the run goes next rather than implying the repair is the end of
    it.
    """

    admissible: bool
    operation: object
    repair_id: object
    bundle_sha: object
    failure: object
    context: object
    retry: object
    refusal: object
    ladder: tuple
    reasons: tuple

    def __post_init__(self):
        undeclared = sorted(set(self.reasons) - _REPAIR_REASON_SET)
        if undeclared:
            raise _refuse("unknown-value",
                          f"a repair plan carries undeclared reason(s) "
                          f"{', '.join(repr(u) for u in undeclared)}")
        if len(set(self.reasons)) != len(self.reasons):
            raise _refuse("duplicate-entry", "a repair plan repeats a reason code")
        if not self.reasons:
            raise _refuse("bounds-exceeded", "a repair plan carries no reason at all")
        # Admissible exactly when the one non-refusal code stands alone, and every other field
        # that only an admissible plan may carry agrees with it. Four facts, one condition: a
        # plan cannot claim a repair while naming a refusal, and cannot refuse while handing
        # back a retry to perform.
        clean = tuple(self.reasons) == (REPAIR_ADMISSIBLE,)
        if self.admissible != clean:
            raise _refuse("value-invalid",
                          f"a repair plan is admissible exactly when nothing refused it; this "
                          f"one says {self.admissible} while carrying {list(self.reasons)}")
        carried = (self.retry is not None, self.operation is not None,
                   self.repair_id is not None, self.refusal is None)
        if any(flag != clean for flag in carried):
            raise _refuse("value-invalid",
                          "a repair plan carries its retry, its operation, its identity and no "
                          "refusal exactly when it is admissible; these disagree")

    def reason(self, code):
        return code in self.reasons


def plan_context_repair(attempt, manifest, bundle, *, checkpoint, assurance, admission_ref,
                        plan_budget, used, ladder, repairs):
    """Is ONE bounded context repair admissible after this failure -> a `ContextRepair`.

    PURE, and pure in the strong sense D13's `select_action` already is: it dispatches nothing,
    opens nothing, writes nothing, starts nothing and asks nothing of a provider or a graph. It
    reports what a coordinator could do and why, and there is no coordinator.

    `attempt` is the failed attempt as `bin/attempt_history.py` projects it -- the authoritative
    event, whose `failure_class` the ledger determined and this module only reads. `manifest` is
    `bin/decision_context.py`'s candidate manifest. `bundle` is a `BundleResolution` from
    `resolve_bundle` above, and it is the ONLY thing that can put a repair in force. The rest
    are the coordinator's own facts: the revision the retry would run at, the assurance the run
    carries, the fresh grant minted for this operation, the kit's declared ceilings and their
    usage, the driver's remaining escalation ladder, and the repairs already recorded.

    EVERY parameter is required and none has a default. A caller states every fact or the call
    does not run, so there is no argument anyone can omit in the permissive direction.

    Every unmet condition is collected rather than short-circuited, for the reason `_unmet`
    above gives: a test asserting one specific refusal cannot be satisfied by a different check
    refusing the same input first.
    """
    record = _failed_attempt(attempt)
    rows = _manifest(manifest)
    in_force, bundle_sha, file_bound = _repair_in_force(bundle)
    kinds = _strings(assurance, "the assurance", ceiling=16)
    unknown = sorted(set(kinds) - set(assurance_kinds()))
    if unknown:
        raise _refuse("unknown-value",
                      f"the assurance names {', '.join(repr(u) for u in unknown)}; the task "
                      f"contract's kinds are {', '.join(assurance_kinds())}")
    rungs = _strings(ladder, "the remaining ladder", ceiling=32)
    taken = _prior_repairs(repairs)
    declared, spent = _budget(plan_budget, used)
    grant = _al().read_ref(admission_ref)
    if grant is None:
        raise _refuse("not-a-reference",
                      "a repair's 'admission_ref' is not a reference; a repair is an admitted "
                      "operation and there is no null that means 'repairing anyway'")
    if checkpoint is not None and (not isinstance(checkpoint, str) or not checkpoint.strip()):
        raise _refuse("value-invalid",
                      "the checkpoint is a revision name, or null when nobody could establish "
                      "one")

    unmet = []

    # ---- the off switch, which is the resolved bundle and nothing else ----
    if not in_force:
        unmet.append("repair-not-in-force")
    elif not isinstance(file_bound, int) or isinstance(file_bound, bool):
        unmet.append("context-bound-undeclared")

    # ---- the failure, read from the trusted event ----
    failure_class = record.get("failure_class")
    if failure_class is None:
        unmet.append("failure-class-unestablished")
    elif failure_class not in REPAIRABLE_FAILURE_CLASSES:
        unmet.append("failure-class-excluded")
    exit_status = record.get("verify_rc")
    if isinstance(exit_status, bool) or not isinstance(exit_status, int) or exit_status == 0:
        unmet.append("failure-not-observed")

    # ---- what the retry must preserve, which it cannot preserve unnamed ----
    model = record.get("dispatched_model")
    if not isinstance(model, str) or not model.strip():
        unmet.append("model-unidentified")
    acceptance = _al().read_ref(record.get("acceptance_ref"))
    if acceptance is None:
        unmet.append("acceptance-unidentified")
    if not kinds:
        unmet.append("assurance-undeclared")

    # ---- a separately identified operation, not the one already spent ----
    spent_grant = _al().read_ref(record.get("admission_ref"))
    if spent_grant is None or spent_grant["id"] == grant["id"]:
        unmet.append("admission-not-separate")
    if taken:
        unmet.append("repair-already-taken")

    # ---- inside the ceilings that already exist, never beside them ----
    contract = _kc()
    drawn = tuple(contract.OPERATION_CAPS.get(REPAIR_OPERATION, ()))
    if any(key not in declared for key in drawn):
        unmet.append("dispatch-cap-undeclared")
    elif contract.blocking_cap(declared, spent, REPAIR_OPERATION) is not None:
        unmet.append("dispatch-cap-reached")

    # ---- the package itself, and the checkpoint it was assembled over ----
    paths = tuple(row.get("path") for row in rows["candidates"])
    if rows["status"] != "candidates" or not paths:
        unmet.append("context-absent")
    elif isinstance(file_bound, int) and not isinstance(file_bound, bool) \
            and len(paths) > file_bound:
        unmet.append("context-over-bound")
    at = ((rows.get("freshness") or {}).get("revision") or {}).get("now")
    if checkpoint is None or not isinstance(at, str) or not at.strip():
        unmet.append("checkpoint-unidentified")
    elif at != checkpoint:
        unmet.append("checkpoint-moved")

    # ---- the evidence, retained whatever the outcome ----
    failure = {
        "kit": record.get("kit"), "run": record.get("run"), "task": record.get("task"),
        "attempt": record.get("attempt"), "source": record.get("source"),
        "ts": record.get("ts"), "result": record.get("result"),
        "failure_class": failure_class,
        # The class is the ledger's determination and this module's basis for reading it is
        # that fact alone. Spelled on the evidence so a reader of the plan never has to take
        # this module's word for where the classification came from.
        "failure_class_basis": "trusted-event" if failure_class else None,
        "verify_rc": record.get("verify_rc"),
        "verify_signature": record.get("verify_signature"),
        "verify_failures": record.get("verify_failures"),
        "artifact": record.get("artifact"),
        "dispatched_model": record.get("dispatched_model"),
        # Carried beside the dispatched model rather than folded into it: what a harness
        # reported running is not always what was asked for, and a repair preserves what was
        # ASKED for. Unknown stays None and is never filled in from the other one.
        "observed_model": record.get("observed_model"),
        "acceptance_ref": None if acceptance is None else dict(acceptance),
        "admission_ref": None if spent_grant is None else dict(spent_grant),
    }
    context = {
        "v": rows["v"], "status": rows["status"],
        "abstention": tuple(rows.get("abstention") or ()),
        "candidates": len(paths), "paths": paths, "bound": file_bound,
        "ref": None, "revision": at,
        # D16's fence, restated where a reader of the plan meets it: a candidate is a place to
        # read. It carries `authority: None` there and gains none by being planned against.
        "navigation": _dx().NO_DEPENDENCY_CLAIM,
        "authority": None,
    }
    try:
        context["ref"] = _dx().context_ref(rows)
    except ValueError:
        # A manifest with no digest is one nobody can point at later. That is a fact about the
        # manifest, recorded as an absent reference rather than raised: the plan's refusal
        # reasons already say whether its candidates were usable.
        context["ref"] = None

    admissible = not unmet
    retry = None
    identity = None
    operation = None
    if admissible:
        material = json.dumps(
            {"attempt": {k: failure[k] for k in ("kit", "run", "task", "attempt")},
             "context": context["ref"], "bundle": bundle_sha, "grant": grant["id"],
             "operation": REPAIR_OPERATION},
            sort_keys=True,
        )
        identity = hashlib.sha256(material.encode("utf-8")).hexdigest()
        operation = REPAIR_OPERATION
        retry = {
            "operation": REPAIR_OPERATION,
            "repair_id": identity,
            # Preserved, all three, and preserved by being COPIED rather than recomputed: there
            # is no parameter on this function through which a different model, a weaker
            # assurance or other criteria could arrive.
            "model": model,
            "assurance": tuple(kinds),
            "acceptance_ref": dict(acceptance),
            "admission_ref": dict(grant),
            "checkpoint": checkpoint,
            "context_ref": context["ref"],
            "context_paths": paths,
            # The evidence of what failed, carried INTO the retry rather than left behind in a
            # report: a retry that cannot see the failure it is repairing is a fresh attempt.
            "failed_attempt": dict(failure),
            "ladder": rungs,
        }

    plan = {"failure": failure, "context": context, "retry": retry, "ladder": rungs}
    _no_dependency_claim(plan, "a context repair plan")
    if retry is not None:
        retry["failed_attempt"] = types.MappingProxyType(retry["failed_attempt"])
        retry = types.MappingProxyType(retry)
    return ContextRepair(
        admissible=admissible, operation=operation, repair_id=identity, bundle_sha=bundle_sha,
        failure=types.MappingProxyType(failure), context=types.MappingProxyType(context),
        retry=retry, ladder=rungs,
        refusal=None if admissible else "; ".join(_REPAIR_TEXT[code] for code in unmet),
        reasons=(REPAIR_ADMISSIBLE,) if admissible else tuple(unmet),
    )
