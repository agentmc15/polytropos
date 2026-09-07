#!/usr/bin/env python3
"""What a harness adapter must answer, and what it is allowed to be unsure about.

`bin/kit_contract.py` holds the decisions that must be the same for every harness. This module
holds the shape of the decisions that must NOT be: what a given host can actually do, how a
dispatch is built for it, and what its result means once normalized.

THE POINT OF A CAPABILITY RECORD IS THAT IT CAN SAY "UNKNOWN". `primitives/harness-matrix.json`
answers "does this product support skills?" — a question about a vendor's feature list, pinned
from aesop's own research and left untouched here. That is not the question a driver needs
answered before it dispatches. It needs three separate ones:

  - does the PRODUCT support this?          (vendor documentation)
  - has POLYTROPOS implemented it?          (this repository)
  - has anyone VERIFIED it on this host?    (a probe, on a date, or never)

Collapsing those into one boolean is how a driver comes to believe it has a control it does
not. `--allowedTools` is the standing example: the product supports it, this repo implements
it, and step 06 found it was silently swallowing the prompt — a control that was "supported"
and "implemented" and did not work. The third column is the one that would have said so.

`unknown` is therefore a first-class value, not a gap to be filled with an optimistic guess. A
capability nobody has verified reports `unknown`, and a caller that needs certainty must treat
that as "no" — which is what `requires()` does.

WHAT ADAPTERS DO NOT DO. They do not re-implement a host's agent loop, its permission model, or
its billing. Each harness keeps its own pricing file and its own model roster, and the three
pricing files never merge. An adapter translates: kit contract in, host-specific argv out,
normalized result back.
"""

import json
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The adapter contract version. Bumped when the operations below change shape.
ADAPTER_VERSION = "polytropos.adapter/1"

#: Operations an adapter may implement. `dispatch` is the only required one; everything else is
#: something a host may or may not expose, and saying so honestly is the job.
OPERATIONS = ("capabilities", "dispatch", "status", "cancel", "normalize_result")

#: Support states, in the order a caller should think about them.
SUPPORTED = "supported"
UNSUPPORTED = "unsupported"
UNKNOWN = "unknown"
#: For a capability that is polytropos's rather than the vendor's -- confining a verify command
#: is not a feature any CLI ships. Distinct from `unknown`, which means the question applies and
#: nobody has answered it; here the question does not apply.
NOT_APPLICABLE = "not-applicable"
SUPPORT_STATES = (SUPPORTED, UNSUPPORTED, UNKNOWN, NOT_APPLICABLE)

#: How a support claim was arrived at. `documented` is a vendor's word; `implemented` is this
#: repository's code; `verified` is someone having run it and recorded the date. They are
#: independent: a thing can be documented and unimplemented, or implemented and unverified.
EVIDENCE_KINDS = ("documented", "implemented", "verified", "none")


class CapabilityError(RuntimeError):
    """An operation was required of an adapter that cannot honestly claim it."""


def capability(name, product=UNKNOWN, implemented=UNKNOWN, verified=UNKNOWN,
               source="", verified_on=None, note=""):
    """One capability row.

    `product`, `implemented` and `verified` are separate on purpose; see the module docstring.
    `source` cites where a `documented` claim comes from, and `verified_on` is the date someone
    actually ran it. A `verified` claim with no date is not a verification, and this says so
    rather than storing a bare `True`.
    """
    for label, value in (("product", product), ("implemented", implemented),
                         ("verified", verified)):
        if value not in SUPPORT_STATES:
            raise ValueError(f"{name}: {label} must be one of {SUPPORT_STATES}, got {value!r}")
    if verified == SUPPORTED and not verified_on:
        raise ValueError(
            f"{name}: verified={SUPPORTED!r} needs verified_on — a verification with no date "
            f"is a belief, and this record exists to keep those apart from findings"
        )
    return {
        "name": name,
        "product": product,
        "implemented": implemented,
        "verified": verified,
        "source": source,
        "verified_on": verified_on,
        "note": note,
    }


def effective(row):
    """The one state a caller should act on: the weakest of the three.

    Deliberately pessimistic. A control that the vendor documents and this repo implements but
    nobody has run is `unknown`, not `supported` — that combination is exactly what the
    swallowed `--allowedTools` flag looked like right up until someone ran it.
    """
    # `not-applicable` drops out rather than counting against: a capability this repo provides
    # is not weakened by the vendor having no opinion about it.
    states = [v for v in (row["product"], row["implemented"], row["verified"])
              if v != NOT_APPLICABLE]
    if not states or UNSUPPORTED in states:
        return UNSUPPORTED if UNSUPPORTED in states else UNKNOWN
    if UNKNOWN in states:
        return UNKNOWN
    return SUPPORTED


class Adapter:
    """Base adapter. Subclasses override what their host can actually do.

    The defaults are the honest ones: every optional operation is unsupported and every
    capability is unknown until a subclass says otherwise with evidence.
    """

    #: Harness identifier, matching the key used in the pricing files and the harness matrix.
    name = "abstract"

    #: How the host is being driven — a CLI, an API, an IDE extension. Capability answers can
    #: differ between a product's modes, so a record that does not say which mode it describes
    #: is not answering the question.
    client_mode = "unknown"

    #: The pricing file this harness reads. Never another harness's: the three never merge.
    pricing_file = None

    def capabilities(self):
        """`{name: capability_row}` for this adapter. Subclasses extend."""
        return {}

    def supports(self, name):
        """The effective state of one capability -- `unknown` when there is no row for it."""
        row = self.capabilities().get(name)
        return effective(row) if row else UNKNOWN

    def requires(self, name):
        """Assert a capability is verified-supported, or raise.

        `unknown` fails here. A caller reaching for this is asking for certainty, and the whole
        reason the record distinguishes unknown from supported is so that "we never checked"
        cannot be spent as though it were "it works".
        """
        state = self.supports(name)
        if state != SUPPORTED:
            row = self.capabilities().get(name)
            detail = ""
            if row:
                detail = (f" (product={row['product']}, implemented={row['implemented']}, "
                          f"verified={row['verified']})")
            raise CapabilityError(
                f"{self.name}: capability {name!r} is {state}{detail}; refusing to rely on it"
            )
        return True

    def build_dispatch(self, task, model_id=None, prompt=""):
        """Host-specific argv for one task. The one operation every adapter must implement."""
        raise NotImplementedError(f"{self.name}: build_dispatch is required")

    def status(self, run_id):
        """Live status for a run, where the host exposes one."""
        raise CapabilityError(f"{self.name}: status queries are not supported")

    def cancel(self, run_id):
        """Cancel a run, where the host exposes it.

        Note what cancelling cannot promise: `bin/proc_runner.py` can stop a process tree, and
        stopping it says nothing about whether the model call it made was already billed.
        """
        raise CapabilityError(f"{self.name}: cancellation is not supported")

    def normalize_result(self, raw):
        """A host's dispatch result as the shared shape -> `{contract, harness, ...}`.

        The default handles `bin/proc_runner.py`'s result dict, which is what every driver's
        runner now returns. An adapter whose host reports something richer overrides this and
        fills the same fields.
        """
        outcome = raw.get("outcome", UNKNOWN)
        return {
            "contract": ADAPTER_VERSION,
            "harness": self.name,
            "client_mode": self.client_mode,
            "outcome": outcome,
            "rc": raw.get("rc"),
            "terminal": bool(raw.get("terminal")),
            "stdout": raw.get("stdout", ""),
            "stderr": raw.get("stderr", ""),
            "detail": raw.get("detail", ""),
            "duration_s": raw.get("duration_s"),
        }


class StubAdapter(Adapter):
    """A conformance target that runs nothing.

    Exists so the adapter contract has a fourth implementation that is not a real harness. Three
    implementations of an interface can agree by coincidence -- they were written by the same
    hand, against the same host family, often by copying each other, which is the history this
    seam was extracted from. A stub that shares none of that either satisfies the contract or
    exposes that the contract was really a description of the three.

    It is also the placeholder for Cursor: when that adapter lands it replaces this as the
    fourth target rather than being the first thing to test the interface.
    """

    name = "stub"
    client_mode = "none"

    def capabilities(self):
        return {
            "dispatch": capability(
                "dispatch", product=SUPPORTED, implemented=SUPPORTED, verified=SUPPORTED,
                source="this module", verified_on=str(date.today()),
                note="returns a canned result; spawns nothing",
            ),
            "status": capability("status", product=UNSUPPORTED, implemented=UNSUPPORTED,
                                 verified=UNSUPPORTED, note="nothing to ask about"),
            "cancel": capability("cancel", product=UNSUPPORTED, implemented=UNSUPPORTED,
                                 verified=UNSUPPORTED, note="nothing to cancel"),
        }

    def build_dispatch(self, task, model_id=None, prompt=""):
        return ["stub-harness", "--task", task.get("id", ""), "--model", model_id or "none"]

    def normalize_result(self, raw):
        return super().normalize_result(raw)


# ---- the operational capability registry -----------------------------------------------------

#: Where the operational view lives. `primitives/harness-matrix.json` is the HISTORICAL aesop
#: matrix and is not touched: it answers a different question (what a product supports), was
#: pinned from aesop's own research at a stated commit, and rewriting it would destroy that
#: provenance. This file sits beside it and answers the operational one.
CAPABILITIES_PATH = REPO_ROOT / "primitives" / "harness-capabilities.json"


def load_capabilities(path=CAPABILITIES_PATH):
    """The operational capability registry, or an empty one if it is absent."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema": None, "harnesses": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("harnesses"), dict):
        return {"schema": None, "harnesses": {}}
    return payload


def registry_capabilities(harness, path=CAPABILITIES_PATH):
    """One harness's rows from the registry, as `capability()` dicts."""
    entry = load_capabilities(path)["harnesses"].get(harness) or {}
    rows = {}
    for name, raw in (entry.get("capabilities") or {}).items():
        rows[name] = capability(
            name,
            product=raw.get("product", UNKNOWN),
            implemented=raw.get("implemented", UNKNOWN),
            verified=raw.get("verified", UNKNOWN),
            source=raw.get("source", ""),
            verified_on=raw.get("verified_on"),
            note=raw.get("note", ""),
        )
    return rows


def render_registry(path=CAPABILITIES_PATH):
    """A human table of every harness's operational capabilities."""
    payload = load_capabilities(path)
    lines = []
    for harness, entry in sorted(payload["harnesses"].items()):
        lines.append(f"## {harness} ({entry.get('client_mode', 'unknown')})")
        rows = registry_capabilities(harness, path)
        width = max((len(n) for n in rows), default=10)
        for name, row in sorted(rows.items()):
            state = effective(row)
            detail = f"product={row['product']} implemented={row['implemented']} verified={row['verified']}"
            when = f" on {row['verified_on']}" if row["verified_on"] else ""
            lines.append(f"  {name:<{width}}  {state:<11} {detail}{when}")
            if row["note"]:
                lines.append(f"  {'':<{width}}  — {row['note']}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _cli(argv=None):
    """`harness_adapter.py` -- print the operational capability registry."""
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--json":
        print(json.dumps(load_capabilities(), indent=2, sort_keys=True))
        return 0
    print(render_registry())
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
