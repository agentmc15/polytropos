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
import importlib.util
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
    """The same object `_runtime` validates, built from named arguments instead of a dict."""
    return _runtime({
        "project": project, "task_class": task_class, "intended_use": intended_use,
        "components": dict(components), "capabilities": list(capabilities),
        "providers": list(providers), "calibration": calibration,
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
