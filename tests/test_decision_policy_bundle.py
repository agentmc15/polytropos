"""D11 -- policy bundles, candidate proposals, and the resolution between them.

`PolicyBundleContractTests` covers two surfaces that split one concern:

  * `bin/decision_contract.py` gained the two RECORD types the shared plan pins -- `PolicyBundle`
    and `CandidateProposal` -- with their own versions, their own canonical digests, and the
    refusals that make a data-only change data-only.
  * `bin/decision_policy.py` is new, and owns the SELECTION over those records: which bundle's
    parameters apply to a runtime, which fallback is taken when none does, and the frozen legacy
    behaviour at the end of every chain. It persists nothing -- the evaluation workbench is this
    repository's one owner of policy persistence, and this module is the read side.

What is under test is not that the fields exist but that the thing refuses what it must:

  * IDENTITY IS CONTENT. A bundle's digest is taken over its canonical form, so key order,
    formatter and parse count cannot move it, and changing any field does. A reference carries
    the BUNDLE's own version -- never the ledger's, never the decision contract's.
  * A FALLBACK IS REQUIRED AND IS NEVER NOTHING. Every bundle says where runtime goes when it
    cannot be used, the chain is bounded and cycle-safe, and legacy terminates every walk.
  * DATA ONLY. The parameter allowlist is the mechanical form of "no candidate edits arbitrary
    Python, shell, module paths, acceptance, permissions or hidden evaluation rules": a banned
    key is refused as an authority field, anything else outside the allowlist as unknown, and
    every value is a scalar of a declared kind so there is no list or nested map for the ban's
    mapping-key sweep to miss.
  * THE HISTORICAL SHAPE LOADS AND IS STILL NOT A BUNDLE. The workbench's pull-only preference
    payload reads back through `describe_legacy_preferences`; `parse_bundle` refuses it by name;
    nothing converts one; and a bundle pinning an older component version parses and then simply
    does not resolve.
  * A BUNDLE GRANTS NOTHING. No field of either record, and no field of a resolution, is one the
    contract bans; the resolution carries no mode and no permission; and the module writes no
    file, starts no process and reaches for no private name of the contract.

`DecisionRequestValidationTests` (D09) and `DecisionValueValidationTests` (D10) own
`tests/test_decision_contract.py` and are untouched by this module.

============================================================================================
 SAFETY CONTRACT
============================================================================================
Nothing here invokes a real `claude`/`codex`/`copilot`/`cursor`/`graphify` binary, reads a real
`~/.claude`/`~/.codex`/`~/.copilot` home, opens a store, writes a file, starts a process or
touches the network. Every fixture is a synthetic dict built in this file. Both modules under
test are pure libraries with no I/O at all, which two tests assert structurally.

ONE LOADER, ON PURPOSE. `bin/` is not a package, so each module here is loaded by path and two
loaders of one file produce two distinct sets of classes. This file therefore reads the contract
through `decision_policy`'s OWN instance, so that a class identity is never accidentally
compared across a boundary -- and one test deliberately builds a SECOND instance to prove the
resolution path is payload-shaped and cannot be broken by that.
"""

import ast
import dataclasses
import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "bin"
POLICY_PATH = BIN_DIR / "decision_policy.py"
CONTRACT_PATH = BIN_DIR / "decision_contract.py"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dp = _load("decision_policy")
dc = dp._contract()          # the SAME contract instance the module under test uses
al = _load("attempt_ledger")
kc = _load("kit_contract")
rg = _load("release_gate")
we = _load("workflow_eval")

PROJECT = "polytropos"
TASK_CLASS = "recovery-cross-module"
USE = "recovery-selection"

#: A synthetic approval-record version. The bundle contract requires that an approval POINTER
#: carry the referenced contract's version; it deliberately does not interpret which contract
#: that is, because the promotion lifecycle owns the approval record and its own version.
APPROVAL_V = "polytropos.policy-approval/1"


def digest(seed):
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def ref(identity, version, sha=None):
    return al.make_ref(identity, sha=digest(identity) if sha is None else sha, version=version)


def bundle_payload(**over):
    payload = {
        "v": dc.BUNDLE_VERSION,
        "id": "bundle-recovery-context-1",
        "parent": ref("bundle-legacy-0", dc.BUNDLE_VERSION),
        "scope": {"project": PROJECT, "task_classes": [TASK_CLASS], "intended_uses": [USE]},
        "components": {"decision_contract": dc.CONTRACT_VERSION,
                       "task_contract": kc.CONTRACT_VERSION,
                       "provider_contract": None},
        "parameters": {"recovery.contract_context_package": True,
                       "recovery.contract_context_files": 4},
        "requirements": {"capabilities": [], "providers": [], "calibration": None},
        "fallback": {"kind": "legacy", "bundle_ref": None},
        "provenance": {"approval_ref": ref("approval-1", APPROVAL_V),
                       "evaluation_ref": ref("manifest-1", we.MANIFEST_VERSION),
                       "rolled_back_from": None},
    }
    payload.update(over)
    return payload


HYPOTHESIS = ("Supplying the callee's interface contract before a same-model retry raises "
              "accepted recovery on cross-module failures without spending more attempts.")
FALSIFICATION = ("Accepted recovery on the held-out cross-module cohort does not exceed the "
                 "frozen arm's rate by the declared margin, at equal or lower total resources.")
TRADEOFF = ("Each retry carries more input, so decision latency and input volume rise even on "
            "the attempts where the added contract material turns out to explain nothing.")


def proposal_payload(**over):
    payload = {
        "v": dc.CANDIDATE_VERSION,
        "id": "cand-contract-context-1",
        "parent": ref("bundle-recovery-context-1", dc.BUNDLE_VERSION),
        "hypothesis": HYPOTHESIS,
        "falsification": FALSIFICATION,
        "tradeoff": TRADEOFF,
        "scope": {"project": PROJECT, "task_classes": [TASK_CLASS], "intended_uses": [USE]},
        "diff": {"recovery.contract_context_package": True},
        "evaluation": {"endpoint": "accepted-recovery", "partition": "promotion",
                       "manifest_ref": ref("manifest-1", we.MANIFEST_VERSION)},
        "evidence": [ref("attempt-a", kc.CONTRACT_VERSION),
                     ref("attempt-b", kc.CONTRACT_VERSION)],
        "counterevidence": [ref("attempt-c", kc.CONTRACT_VERSION)],
        "rollback": {"kind": "legacy", "bundle_ref": None},
    }
    payload.update(over)
    return payload


def preference_payload(**over):
    """The evaluation workbench's own applied-preference shape, as it writes it today."""
    payload = {
        "v": we.POLICY_VERSION,
        "version": 3,
        "applied_at": "2026-09-16T00:00:00Z",
        "proposal": "prop-2026-09-16-abc123",
        "source_runs": ["2026-09-16-1b4c"],
        "evidence_tasks": ["T1", "T2"],
        "defaults": {"workflow": "kit"},
        "by_task_class": {"S": {"policy": "assured"}},
        "consumption": "pull-only: no driver reads this file until wired on purpose",
        "labels": ["mutation-repair"],
    }
    payload.update(over)
    return payload


class PolicyBundleContractTests(unittest.TestCase):

    # ---- fixtures ---------------------------------------------------------------------------

    def bundle(self, **over):
        return dc.parse_bundle(bundle_payload(**over))

    def proposal(self, **over):
        return dc.parse_proposal(proposal_payload(**over))

    def facts(self, **over):
        base = {"project": PROJECT, "task_class": TASK_CLASS, "intended_use": USE,
                "components": {"decision_contract": dc.CONTRACT_VERSION,
                               "task_contract": kc.CONTRACT_VERSION,
                               "provider_contract": None},
                "capabilities": (), "providers": (), "calibration": None}
        base.update(over)
        return dp.runtime_facts(**base)

    def refusal(self, code, callable_, *args, **kwargs):
        with self.assertRaises(dc.ContractError) as caught:
            callable_(*args, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception

    def resolve(self, payloads, pin=None, **facts):
        payloads = list(payloads)
        if pin is None:
            pin = dp.bundle_ref(payloads[0])
        return dp.resolve_bundle(pin, payloads, self.facts(**facts))

    def chain(self, identities, *, met_last=True, tail=None):
        """A fallback chain `identities[0] -> identities[1] -> ... -> tail or legacy`.

        Every link but the last is unmet, by the one requirement that is independent of scope,
        components and capabilities: it points at no approval. So what moves the walk along is
        the fallback, not an accident of the fixture.
        """
        payloads = []
        pointer = tail
        for index, identity in enumerate(reversed(identities)):
            last = index == 0
            fallback = ({"kind": "legacy", "bundle_ref": None} if pointer is None
                        else {"kind": "bundle", "bundle_ref": pointer})
            over = {"id": identity, "fallback": fallback}
            if not (last and met_last):
                over["provenance"] = {"approval_ref": None, "evaluation_ref": None,
                                      "rolled_back_from": None}
            payload = bundle_payload(**over)
            payloads.append(payload)
            pointer = dp.bundle_ref(payload)
        payloads.reverse()
        return payloads

    # ---- identity is content -----------------------------------------------------------------

    def test_a_bundle_digests_its_content_and_not_the_shape_of_the_text_it_arrived_in(self):
        payload = bundle_payload()
        reordered = dict(reversed(list(payload.items())))
        self.assertNotEqual(list(payload), list(reordered), "the fixture must actually reorder")
        self.assertEqual(dc.parse_bundle(payload).sha(), dc.parse_bundle(reordered).sha())
        # Through the wire, too: the canonical form is what is digested, never anyone's spacing.
        spaced = json.loads(json.dumps(payload, indent=4))
        self.assertEqual(dc.parse_bundle(spaced).sha(), dc.parse_bundle(payload).sha())
        # And a round trip is a fixed point, so a stored bundle keeps the identity it was
        # written under rather than acquiring a new one on every read.
        once = dc.parse_bundle(payload)
        self.assertEqual(dc.parse_bundle(once.to_payload()).sha(), once.sha())
        self.assertEqual(once.sha(), dc.parse_bundle(payload).sha())

    def test_changing_any_part_of_a_bundle_changes_its_digest(self):
        base = self.bundle().sha()
        mutations = [
            ("id", {"id": "bundle-recovery-context-2"}),
            ("parent", {"parent": ref("bundle-other-0", dc.BUNDLE_VERSION)}),
            ("scope", {"scope": {"project": PROJECT, "task_classes": ["other-class"],
                                 "intended_uses": [USE]}}),
            ("components", {"components": {"decision_contract": dc.CONTRACT_VERSION,
                                           "task_contract": kc.CONTRACT_VERSION,
                                           "provider_contract": "polytropos.provider/1"}}),
            ("parameters", {"parameters": {"recovery.contract_context_package": False,
                                           "recovery.contract_context_files": 4}}),
            ("parameters-count", {"parameters": {"recovery.contract_context_package": True,
                                                 "recovery.contract_context_files": 5}}),
            ("requirements", {"requirements": {"capabilities": ["dispatch"], "providers": [],
                                               "calibration": None}}),
            ("fallback", {"fallback": {"kind": "bundle",
                                       "bundle_ref": ref("bundle-legacy-0",
                                                         dc.BUNDLE_VERSION)}}),
            ("provenance", {"provenance": {"approval_ref": ref("approval-2", APPROVAL_V),
                                           "evaluation_ref": ref("manifest-1",
                                                                 we.MANIFEST_VERSION),
                                           "rolled_back_from": None}}),
        ]
        self.assertTrue(mutations, "the mutations are what this test compares against")
        seen = {base}
        for name, over in mutations:
            with self.subTest(field=name):
                moved = self.bundle(**over).sha()
                self.assertNotEqual(moved, base)
                self.assertNotIn(moved, seen, "two different bundles digest the same")
                seen.add(moved)

    def test_a_proposal_digests_its_content_the_same_way_and_never_collides_with_a_bundle(self):
        payload = proposal_payload()
        reordered = dict(reversed(list(payload.items())))
        self.assertEqual(dc.parse_proposal(payload).sha(), dc.parse_proposal(reordered).sha())
        once = dc.parse_proposal(payload)
        self.assertEqual(dc.parse_proposal(once.to_payload()).sha(), once.sha())
        self.assertNotEqual(once.sha(), self.bundle().sha())
        moved = self.proposal(diff={"recovery.contract_context_files": 8}).sha()
        self.assertNotEqual(moved, once.sha())

    def test_a_bundle_reference_carries_the_bundles_own_version_and_not_a_neighbours(self):
        payload = bundle_payload()
        pointer = dp.bundle_ref(payload)
        self.assertEqual(sorted(pointer), sorted(al.REF_FIELDS))
        self.assertEqual(pointer["id"], payload["id"])
        self.assertEqual(pointer["sha"], dc.parse_bundle(payload).sha())
        self.assertEqual(pointer["v"], dc.BUNDLE_VERSION)
        # Three versions that would each be wrong here, and are all in scope to be confused.
        for other in (al.LEDGER_VERSION, dc.CONTRACT_VERSION, dc.CANDIDATE_VERSION):
            with self.subTest(other=other):
                self.assertNotEqual(pointer["v"], other)
        # A parsed bundle and its payload name the same content.
        self.assertEqual(dp.bundle_ref(dc.parse_bundle(payload)), pointer)

    def test_a_reference_notices_content_that_moved_under_it(self):
        payload = bundle_payload()
        pointer = dp.bundle_ref(payload)
        self.assertTrue(dp.matches_ref(payload, pointer))
        moved = bundle_payload(parameters={"recovery.contract_context_files": 9})
        self.assertFalse(dp.matches_ref(moved, pointer))
        # A pointer with no digest pins nothing, so it can never confirm a match.
        self.assertFalse(dp.matches_ref(payload, al.make_ref(payload["id"],
                                                             version=dc.BUNDLE_VERSION)))
        self.assertFalse(dp.matches_ref(payload, "not-a-reference"))
        # Content that will not parse is not the content the pointer named.
        self.assertFalse(dp.matches_ref(bundle_payload(fallback=None), pointer))

    def test_both_new_versions_are_declared_on_the_release_surface_in_their_own_right(self):
        rows = {r["contract"]: r for r in rg.contract_versions()}
        for label, attr, value in (("policy bundle", "BUNDLE_VERSION", dc.BUNDLE_VERSION),
                                   ("candidate proposal", "CANDIDATE_VERSION",
                                    dc.CANDIDATE_VERSION)):
            with self.subTest(contract=label):
                self.assertIn((label, "decision_contract", attr), rg.VERSION_SOURCES)
                self.assertEqual(rows[label]["version"], value)
                self.assertEqual(rows[label]["owner"], "bin/decision_contract.py")
        # Separate rows, never an overload of the decision contract's own version: a change to
        # one of these must not read as a change to the four objects D09 defined.
        self.assertNotEqual(dc.BUNDLE_VERSION, dc.CONTRACT_VERSION)
        self.assertNotEqual(dc.CANDIDATE_VERSION, dc.CONTRACT_VERSION)
        self.assertNotEqual(dc.BUNDLE_VERSION, dc.CANDIDATE_VERSION)
        self.assertEqual(rows["decision contract"]["version"], dc.CONTRACT_VERSION)

    # ---- a fallback is required, and is never nothing -----------------------------------------

    def test_a_bundle_must_say_what_it_falls_back_to(self):
        self.refusal("missing-field", dc.parse_bundle,
                     bundle_payload(fallback={"kind": "legacy"}))
        self.refusal("wrong-type", dc.parse_bundle, bundle_payload(fallback=None))
        self.refusal("wrong-type", dc.parse_bundle, bundle_payload(fallback="legacy"))
        self.refusal("unknown-value", dc.parse_bundle,
                     bundle_payload(fallback={"kind": "none", "bundle_ref": None}))
        self.refusal("unknown-field", dc.parse_bundle,
                     bundle_payload(fallback={"kind": "legacy", "bundle_ref": None,
                                              "note": "x"}))
        # `legacy` and a pointer are mutually exclusive: it is one or the other.
        self.refusal("value-invalid", dc.parse_bundle,
                     bundle_payload(fallback={"kind": "legacy",
                                              "bundle_ref": ref("b0", dc.BUNDLE_VERSION)}))
        # `bundle` needs an actual pinned pointer.
        self.refusal("not-a-reference", dc.parse_bundle,
                     bundle_payload(fallback={"kind": "bundle", "bundle_ref": None}))
        self.refusal("value-invalid", dc.parse_bundle,
                     bundle_payload(fallback={"kind": "bundle",
                                              "bundle_ref": al.make_ref(
                                                  "b0", version=dc.BUNDLE_VERSION)}))
        self.refusal("value-invalid", dc.parse_bundle,
                     bundle_payload(fallback={"kind": "bundle",
                                              "bundle_ref": al.make_ref("b0",
                                                                        sha=digest("b0"))}))
        self.refusal("unknown-value", dc.parse_bundle,
                     bundle_payload(fallback={"kind": "bundle",
                                              "bundle_ref": ref("b0", dc.CONTRACT_VERSION)}))
        # And a bundle cannot be its own fallback -- the chain would never reach legacy.
        self.refusal("value-invalid", dc.parse_bundle,
                     bundle_payload(fallback={"kind": "bundle",
                                              "bundle_ref": ref("bundle-recovery-context-1",
                                                                dc.BUNDLE_VERSION)}))
        # The positive case, so the refusals above are not the only shape this accepts.
        self.assertEqual(self.bundle().fallback["kind"], "legacy")

    def test_a_proposal_must_say_what_a_rollback_returns_to(self):
        self.refusal("missing-field", dc.parse_proposal, proposal_payload(rollback={}))
        self.refusal("wrong-type", dc.parse_proposal, proposal_payload(rollback=None))
        self.refusal("not-a-reference", dc.parse_proposal,
                     proposal_payload(rollback={"kind": "bundle", "bundle_ref": None}))
        rolled = self.proposal(rollback={"kind": "bundle",
                                         "bundle_ref": ref("bundle-legacy-0",
                                                           dc.BUNDLE_VERSION)})
        self.assertEqual(rolled.rollback["bundle_ref"]["id"], "bundle-legacy-0")

    def test_a_bundle_that_meets_every_requirement_is_selected(self):
        # The positive control for every "ends at legacy" case below. Without it a resolver that
        # always returned legacy would satisfy all of them.
        payload = bundle_payload()
        resolution = self.resolve([payload])
        self.assertEqual(resolution.source, "pinned")
        self.assertIsNotNone(resolution.bundle)
        self.assertEqual(resolution.bundle.id, payload["id"])
        self.assertEqual(resolution.reasons, ("selected",))
        self.assertEqual(resolution.chain, (payload["id"],))
        self.assertEqual(dict(resolution.parameters), payload["parameters"])
        self.assertEqual(resolution.ref["sha"], dc.parse_bundle(payload).sha())

    def test_an_unusable_bundle_hands_off_to_the_fallback_it_declared(self):
        payloads = self.chain(["bundle-head", "bundle-tail"])
        resolution = self.resolve(payloads)
        self.assertEqual(resolution.source, "fallback")
        self.assertEqual(resolution.bundle.id, "bundle-tail")
        self.assertEqual(resolution.chain, ("bundle-head", "bundle-tail"))
        self.assertIn("approval-absent", resolution.reasons)
        self.assertIn("selected", resolution.reasons)

    def test_a_chain_whose_every_link_is_unusable_ends_at_the_legacy_behaviour(self):
        payloads = self.chain(["bundle-head", "bundle-tail"], met_last=False)
        resolution = self.resolve(payloads)
        self.assertEqual(resolution.source, "legacy")
        self.assertIsNone(resolution.bundle)
        self.assertEqual(dict(resolution.parameters), {})
        self.assertIn("fallback-legacy", resolution.reasons)
        self.assertEqual(resolution.chain, ("bundle-head", "bundle-tail"))

    def test_a_fallback_that_loops_back_ends_at_legacy_instead_of_walking_forever(self):
        # A content-addressed cycle cannot be built honestly -- each link's digest depends on the
        # next -- so this is the realistic form: the tail pins a STALE digest of the head, which
        # is a lineage that loops. The id repeat is caught before the digest is even compared.
        stale_head = al.make_ref("bundle-head", sha=digest("stale"), version=dc.BUNDLE_VERSION)
        payloads = self.chain(["bundle-head", "bundle-tail"], met_last=False, tail=stale_head)
        resolution = self.resolve(payloads)
        self.assertEqual(resolution.source, "legacy")
        self.assertIn("fallback-cycle", resolution.reasons)
        self.assertEqual(resolution.chain, ("bundle-head", "bundle-tail"))

    def test_a_fallback_chain_longer_than_the_bound_ends_at_legacy(self):
        identities = [f"bundle-link-{n:02d}" for n in range(dp.MAX_FALLBACK_DEPTH + 3)]
        payloads = self.chain(identities, met_last=False)
        resolution = self.resolve(payloads)
        self.assertEqual(resolution.source, "legacy")
        self.assertIn("fallback-depth-exceeded", resolution.reasons)
        self.assertEqual(len(resolution.chain), dp.MAX_FALLBACK_DEPTH + 1)
        self.assertNotIn("fallback-cycle", resolution.reasons)

    def test_content_that_moved_under_its_pin_goes_to_legacy_and_not_to_its_own_fallback(self):
        # The bundle's own fallback pointer was written by whoever rewrote the bundle, so it is
        # not followed. The tail here is perfectly usable and is still not selected.
        payloads = self.chain(["bundle-head", "bundle-tail"])
        rewritten = dict(payloads[0])
        rewritten["parameters"] = {"recovery.contract_context_files": 64}
        resolution = dp.resolve_bundle(dp.bundle_ref(payloads[0]),
                                       [rewritten, payloads[1]], self.facts())
        self.assertEqual(resolution.source, "legacy")
        self.assertIn("bundle-content-mismatch", resolution.reasons)
        self.assertEqual(resolution.chain, ("bundle-head",))
        self.assertNotIn("selected", resolution.reasons)

    def test_a_pin_naming_a_bundle_nobody_has_ends_at_legacy(self):
        resolution = dp.resolve_bundle(ref("bundle-absent", dc.BUNDLE_VERSION), [], self.facts())
        self.assertEqual(resolution.source, "legacy")
        self.assertEqual(resolution.reasons, ("bundle-unknown",))

    def test_a_payload_that_will_not_parse_ends_at_legacy_rather_than_raising(self):
        broken = bundle_payload(scope={"project": PROJECT, "task_classes": [],
                                       "intended_uses": [USE]})
        resolution = dp.resolve_bundle(al.make_ref(broken["id"], sha=digest("whatever"),
                                                   version=dc.BUNDLE_VERSION),
                                       [broken], self.facts())
        self.assertEqual(resolution.source, "legacy")
        self.assertEqual(resolution.reasons, ("bundle-invalid",))

    def test_no_pin_is_the_legacy_default_and_a_malformed_pin_is_too(self):
        empty = dp.resolve_bundle(None, [bundle_payload()], self.facts())
        self.assertEqual(empty.source, "legacy")
        self.assertEqual(empty.reasons, ("no-pin",))
        self.assertEqual(empty.chain, ())
        for name, pin in (("not a reference", "bundle-recovery-context-1"),
                          ("no digest", al.make_ref("bundle-recovery-context-1",
                                                    version=dc.BUNDLE_VERSION)),
                          ("another contract", ref("bundle-recovery-context-1",
                                                   dc.CONTRACT_VERSION))):
            with self.subTest(pin=name):
                resolution = dp.resolve_bundle(pin, [bundle_payload()], self.facts())
                self.assertEqual(resolution.source, "legacy")
                self.assertEqual(resolution.reasons, ("pin-not-a-reference",))

    # ---- one unmet requirement at a time ------------------------------------------------------

    def test_a_bundle_pointing_at_no_approval_is_never_selected(self):
        resolution = self.resolve([bundle_payload(
            provenance={"approval_ref": None, "evaluation_ref": None,
                        "rolled_back_from": None})])
        self.assertEqual(resolution.source, "legacy")
        self.assertEqual(resolution.reasons, ("approval-absent", "fallback-legacy"))

    def test_a_bundle_pinning_a_component_version_the_runtime_is_not_running_is_not_selected(self):
        resolution = self.resolve(
            [bundle_payload()],
            components={"decision_contract": "polytropos.decision/9",
                        "task_contract": kc.CONTRACT_VERSION, "provider_contract": None})
        self.assertEqual(resolution.source, "legacy")
        self.assertEqual(resolution.reasons, ("component-mismatch", "fallback-legacy"))
        # A component the bundle leaves null is one it does not depend on, so a runtime that has
        # one anyway is not a mismatch.
        still = self.resolve([bundle_payload()],
                             components={"decision_contract": dc.CONTRACT_VERSION,
                                         "task_contract": kc.CONTRACT_VERSION,
                                         "provider_contract": "polytropos.provider/1"})
        self.assertEqual(still.reasons, ("selected",))

    def test_a_capability_the_registry_has_not_verified_is_not_a_capability(self):
        needs = bundle_payload(requirements={"capabilities": ["protected-experiments"],
                                             "providers": [], "calibration": None})
        resolution = self.resolve([needs])
        self.assertEqual(resolution.source, "legacy")
        self.assertEqual(resolution.reasons, ("capability-unverified", "fallback-legacy"))
        met = self.resolve([needs], capabilities=("protected-experiments",))
        self.assertEqual(met.reasons, ("selected",))

    def test_a_bundle_requiring_a_provider_the_runtime_may_not_use_is_not_selected(self):
        needs = bundle_payload(
            requirements={"capabilities": [], "providers": ["shadow-advisor"],
                          "calibration": None},
            components={"decision_contract": dc.CONTRACT_VERSION,
                        "task_contract": kc.CONTRACT_VERSION,
                        "provider_contract": "polytropos.provider/1"})
        resolution = self.resolve([needs],
                                  components={"decision_contract": dc.CONTRACT_VERSION,
                                              "task_contract": kc.CONTRACT_VERSION,
                                              "provider_contract": "polytropos.provider/1"})
        self.assertEqual(resolution.source, "legacy")
        self.assertEqual(resolution.reasons, ("provider-ineligible", "fallback-legacy"))
        met = self.resolve([needs], providers=("shadow-advisor",),
                           components={"decision_contract": dc.CONTRACT_VERSION,
                                       "task_contract": kc.CONTRACT_VERSION,
                                       "provider_contract": "polytropos.provider/1"})
        self.assertEqual(met.reasons, ("selected",))

    def test_a_bundle_requiring_a_calibrator_the_runtime_does_not_hold_is_not_selected(self):
        calibrator = ref("calib-1", "polytropos.calibration/1")
        needs = bundle_payload(requirements={"capabilities": [], "providers": [],
                                             "calibration": calibrator})
        absent = self.resolve([needs])
        self.assertEqual(absent.reasons, ("calibration-unmet", "fallback-legacy"))
        # A DIFFERENT calibrator is not the one required, and neither is the same id refit.
        other = self.resolve([needs], calibration=ref("calib-2", "polytropos.calibration/1"))
        self.assertEqual(other.reasons, ("calibration-unmet", "fallback-legacy"))
        refit = self.resolve([needs], calibration=al.make_ref(
            "calib-1", sha=digest("refit"), version="polytropos.calibration/1"))
        self.assertEqual(refit.reasons, ("calibration-unmet", "fallback-legacy"))
        met = self.resolve([needs], calibration=calibrator)
        self.assertEqual(met.reasons, ("selected",))

    def test_a_bundle_is_not_used_outside_the_scope_it_was_approved_for(self):
        cases = {"project": {"project": "some-other-repo"},
                 "task class": {"task_class": "unrelated-class"},
                 "intended use": {"intended_use": "proposal-evidence"}}
        self.assertTrue(cases, "the out-of-scope cases are what this test sweeps")
        for name, over in cases.items():
            with self.subTest(dimension=name):
                resolution = self.resolve([bundle_payload()], **over)
                self.assertEqual(resolution.source, "legacy")
                self.assertEqual(resolution.reasons, ("out-of-scope", "fallback-legacy"))

    def test_every_unmet_requirement_is_reported_and_not_just_the_first(self):
        # Short-circuiting would make each of the tests above satisfiable by whichever check
        # happened to run first, which is the exact masking this kit has been bitten by twice.
        resolution = self.resolve(
            [bundle_payload(provenance={"approval_ref": None, "evaluation_ref": None,
                                        "rolled_back_from": None},
                            requirements={"capabilities": ["nope"], "providers": [],
                                          "calibration": None})],
            project="some-other-repo")
        for code in ("approval-absent", "capability-unverified", "out-of-scope"):
            with self.subTest(reason=code):
                self.assertIn(code, resolution.reasons)

    # ---- data only --------------------------------------------------------------------------

    def test_an_authority_field_is_refused_wherever_it_appears_in_a_bundle(self):
        self.assertTrue(dc.BANNED_FIELDS, "an empty ban would make every case below vacuous")
        places = {
            "top level": lambda: bundle_payload(**{"approve": True}),
            "parameters": lambda: bundle_payload(parameters={"permissions": "all"}),
            "scope": lambda: bundle_payload(scope={"project": PROJECT,
                                                   "task_classes": [TASK_CLASS],
                                                   "intended_uses": [USE], "grant": "x"}),
            "requirements": lambda: bundle_payload(requirements={"capabilities": [],
                                                                 "providers": [],
                                                                 "calibration": None,
                                                                 "trusted_host": True}),
            "components": lambda: bundle_payload(components={"decision_contract": "x",
                                                             "budget": "y"}),
            "fallback": lambda: bundle_payload(fallback={"kind": "legacy", "bundle_ref": None,
                                                         "max_dispatches": 9}),
            "provenance": lambda: bundle_payload(provenance={"approval_ref": None,
                                                             "evaluation_ref": None,
                                                             "rolled_back_from": None,
                                                             "skip_review": True}),
        }
        self.assertTrue(places, "the placements are what this test sweeps")
        for name, build in places.items():
            with self.subTest(where=name):
                self.refusal("authority-field", dc.parse_bundle, build())
        # A period does not launder one, which is the bypass D09 shipped and then closed.
        self.refusal("authority-field", dc.parse_bundle,
                     bundle_payload(parameters={"budget.x": 1}))

    def test_a_candidate_may_not_change_code_shell_imports_permissions_or_the_rules(self):
        cases = {
            "code": ("code", "print(1)", "authority-field"),
            "shell": ("shell", "/bin/sh", "authority-field"),
            "import": ("import", "os", "authority-field"),
            "module path": ("module", "bin.workflow_eval", "authority-field"),
            "a patch": ("patch", "diff --git", "authority-field"),
            "argv": ("argv", "x", "authority-field"),
            "permissions": ("permissions", "all", "authority-field"),
            "an acceptance override": ("acceptance_override", True, "authority-field"),
            "review": ("skip_review", True, "authority-field"),
            "a namespaced eval": ("hidden.eval", "x", "authority-field"),
            "acceptance": ("acceptance", "always", "unknown-field"),
            "the evaluation rules": ("evaluation_rules", "lenient", "unknown-field"),
            "hidden labels": ("hidden_labels", "x", "unknown-field"),
            "a price": ("pricing", 0.0, "unknown-field"),
            "the procedure itself": ("improvement_procedure", "x", "unknown-field"),
        }
        self.assertTrue(cases, "the rejected changes are what this test sweeps")
        for name, (key, value, code) in cases.items():
            with self.subTest(change=name):
                self.refusal(code, dc.parse_proposal, proposal_payload(diff={key: value}))
                self.refusal(code, dc.parse_bundle, bundle_payload(parameters={key: value}))

    def test_a_parameter_value_is_a_scalar_of_its_declared_kind_and_is_never_coerced(self):
        cases = {
            "a string for a boolean": ({"recovery.contract_context_package": "true"},
                                       "wrong-type"),
            "a number for a boolean": ({"recovery.contract_context_package": 1}, "wrong-type"),
            "a string for a count": ({"recovery.contract_context_files": "4"}, "wrong-type"),
            "a float for a count": ({"recovery.contract_context_files": 4.0}, "wrong-type"),
            "a boolean for a count": ({"recovery.contract_context_files": True}, "wrong-type"),
            "a negative count": ({"recovery.contract_context_files": -1}, "value-invalid"),
            "an unbounded count": ({"recovery.contract_context_files":
                                    dc.MAX_PARAMETER_VALUE + 1}, "bounds-exceeded"),
            "a boolean for a label": ({"routing.default_workflow": True}, "wrong-type"),
            # The two shapes the ban's mapping-key sweep does not reach. Neither can occur here,
            # because a parameter is a scalar and a list or a nested map is refused by type.
            "a list": ({"routing.default_workflow": ["kit", "direct"]}, "wrong-type"),
            "a nested object": ({"routing.default_workflow": {"approve": True}}, "wrong-type"),
        }
        self.assertTrue(cases, "the rejected values are what this test sweeps")
        for name, (diff, code) in cases.items():
            with self.subTest(value=name):
                self.refusal(code, dc.parse_proposal, proposal_payload(diff=diff))
        self.assertEqual(sorted(set(dc.DIFF_PARAMETERS.values())),
                         sorted(set(dc.PARAMETER_KINDS)),
                         "every declared kind is in use and no parameter takes an undeclared one")

    def test_a_bundle_and_a_proposal_share_one_parameter_allowlist(self):
        self.assertTrue(dc.DIFF_PARAMETERS, "an empty allowlist would make this vacuous")
        for name in dc.DIFF_PARAMETERS:
            with self.subTest(parameter=name):
                value = {"boolean": True, "count": 2,
                         "label": "some-value"}[dc.DIFF_PARAMETERS[name]]
                self.assertEqual(dict(self.bundle(parameters={name: value}).parameters),
                                 {name: value})
                self.assertEqual(dict(self.proposal(diff={name: value}).diff), {name: value})
        # A parameter a bundle may carry that a proposal may not change, or the reverse, would
        # be a policy nobody can reach or a change nobody can hold. There is one list.
        self.refusal("unknown-field", dc.parse_bundle,
                     bundle_payload(parameters={"recovery.something_else": True}))
        self.refusal("unknown-field", dc.parse_proposal,
                     proposal_payload(diff={"recovery.something_else": True}))

    def test_a_proposal_changes_at_least_one_parameter_and_never_more_than_the_allowlist(self):
        self.refusal("bounds-exceeded", dc.parse_proposal, proposal_payload(diff={}))
        # A bundle, unlike a proposal, may carry none: that is the baseline a rollback names.
        self.assertEqual(dict(self.bundle(parameters={}).parameters), {})
        # More entries than the allowlist has is refused on the count, before any one of them is
        # looked at -- so a payload cannot be a channel by repeating legitimate-looking keys.
        oversized = {"boolean": True, "count": 1,
                     "label": "x"}
        every = {name: oversized[kind] for name, kind in dc.DIFF_PARAMETERS.items()}
        self.assertEqual(len(every), len(dc.DIFF_PARAMETERS))
        self.assertEqual(sorted(self.proposal(diff=every).diff), sorted(dc.DIFF_PARAMETERS))
        self.refusal("bounds-exceeded", dc.parse_proposal,
                     proposal_payload(diff=dict(every, **{"one.too.many": True})))

    def test_a_payload_that_does_not_say_which_contract_wrote_it_is_read_by_none(self):
        for parse, payload in ((dc.parse_bundle, bundle_payload()),
                               (dc.parse_proposal, proposal_payload())):
            with self.subTest(record=parse.__name__):
                self.refusal("missing-field", parse,
                             {k: v for k, v in payload.items() if k != "v"})
                self.refusal("wrong-type", parse, dict(payload, v=1))
                self.refusal("wrong-type", parse, [payload])
        # Each parser reads its own version and refuses to guess at the other's field meanings,
        # which is the whole reason the two versions are separate.
        self.refusal("unknown-value", dc.parse_bundle,
                     bundle_payload(v=dc.CANDIDATE_VERSION))
        self.refusal("unknown-value", dc.parse_bundle, bundle_payload(v=dc.CONTRACT_VERSION))
        self.refusal("unknown-value", dc.parse_proposal,
                     proposal_payload(v=dc.BUNDLE_VERSION))
        self.refusal("wrong-type", dp.bundle_ref, 5)
        self.refusal("wrong-type", dp.bundle_ref, "bundle-recovery-context-1")

    def test_no_field_these_records_define_is_one_the_contract_bans(self):
        defined = set()
        for name in dir(dc):
            if name.endswith("_KEYS") and isinstance(getattr(dc, name), tuple):
                defined.update(getattr(dc, name))
        defined.update(dc.DIFF_PARAMETERS)
        defined.update(dc.COMPONENT_KEYS)
        self.assertTrue(defined, "the key tuples are what this test sweeps")
        self.assertTrue(dc.BANNED_FIELDS, "an empty ban has nothing for this sweep to collide")
        self.assertEqual(sorted(k for k in defined if dc._is_banned_key(k)), [])
        # And the ban still matches its own plain spellings, so this is not passing because the
        # comparison quietly stopped banning anything.
        self.assertEqual(sorted(n for n in dc.BANNED_FIELDS if not dc._is_banned_key(n)), [])
        # `diff` is deliberately not banned, which is what makes a data-only diff expressible.
        self.assertNotIn("diff", dc.BANNED_FIELDS)
        self.assertFalse(dc._is_banned_key("diff"))

    # ---- falsifiable, evidenced, held-out -----------------------------------------------------

    def test_a_proposal_states_a_claim_that_could_turn_out_to_be_wrong(self):
        self.refusal("value-invalid", dc.parse_proposal,
                     proposal_payload(hypothesis="context helps"))
        # Enough words to clear the word floor and far too few characters to have claimed
        # anything. Without this the character floor is never isolated: every other short
        # hypothesis here is also short of words, and the word floor refuses it first.
        sparse = "does it or does it not"
        self.assertGreaterEqual(len(sparse.split()), dc.MIN_STATEMENT_WORDS)
        self.assertLess(len(sparse), dc.MIN_STATEMENT_CHARS)
        self.refusal("value-invalid", dc.parse_proposal, proposal_payload(hypothesis=sparse))
        # Long enough to clear the character floor and still not a sentence, which is the case
        # the word floor exists for: without it, running the words together passes.
        self.refusal("value-invalid", dc.parse_proposal,
                     proposal_payload(hypothesis="Supplyingtheinterfacecontract helps "
                                                 "recovery a lot"))
        # Long enough and wordy enough to clear BOTH floors above -- which is what it takes to
        # reach this branch at all -- and still nothing but the id with punctuation sprinkled
        # through it. A shorter restatement is refused by the character floor first, so it
        # would prove this check is there when it is not.
        restated = "Cand -- contract -- context -- 1 -- -- -- --"
        self.assertGreaterEqual(len(restated), dc.MIN_STATEMENT_CHARS)
        self.assertGreaterEqual(len(restated.split()), dc.MIN_STATEMENT_WORDS)
        self.refusal("value-invalid", dc.parse_proposal,
                     proposal_payload(hypothesis=restated))
        # A falsification that restates the hypothesis names no observation that would refute it.
        self.refusal("value-invalid", dc.parse_proposal,
                     proposal_payload(falsification=HYPOTHESIS))
        self.refusal("value-invalid", dc.parse_proposal,
                     proposal_payload(falsification=HYPOTHESIS.upper() + "!!!"))
        # Nor does a tradeoff that restates either of them name a cost.
        self.refusal("value-invalid", dc.parse_proposal, proposal_payload(tradeoff=HYPOTHESIS))
        self.refusal("value-invalid", dc.parse_proposal,
                     proposal_payload(tradeoff=FALSIFICATION))
        self.assertEqual(self.proposal().falsification, FALSIFICATION)

    def test_a_proposal_cites_recurring_evidence_and_the_evidence_against_it(self):
        one = [ref("attempt-a", kc.CONTRACT_VERSION)]
        self.refusal("bounds-exceeded", dc.parse_proposal, proposal_payload(evidence=one))
        self.refusal("bounds-exceeded", dc.parse_proposal, proposal_payload(evidence=[]))
        self.assertEqual(dc.MIN_EVIDENCE_REFS, 2)
        # The same attempt twice is one observation, not two.
        twice = [ref("attempt-a", kc.CONTRACT_VERSION), ref("attempt-a", kc.CONTRACT_VERSION)]
        self.refusal("duplicate-entry", dc.parse_proposal, proposal_payload(evidence=twice))
        # And it cannot be filed on both sides, which would make each side's count meaningless.
        self.refusal("duplicate-entry", dc.parse_proposal,
                     proposal_payload(counterevidence=[ref("attempt-a", kc.CONTRACT_VERSION)]))
        # Evidence pins the bytes it cites; an unpinned pointer cannot notice them changing.
        self.refusal("value-invalid", dc.parse_proposal,
                     proposal_payload(evidence=[al.make_ref("attempt-a", version="x/1"),
                                                ref("attempt-b", kc.CONTRACT_VERSION)]))
        # "Looked, found none" is a claim, recorded as an empty list rather than an omission.
        self.assertEqual(self.proposal(counterevidence=[]).counterevidence, ())
        self.refusal("missing-field", dc.parse_proposal,
                     {k: v for k, v in proposal_payload().items() if k != "counterevidence"})

    def test_a_proposal_is_evaluated_on_material_no_fit_has_seen(self):
        for partition in dc.EVIDENCE_PARTITIONS:
            with self.subTest(partition=partition):
                parsed = self.proposal(evaluation={"endpoint": "accepted-recovery",
                                                   "partition": partition,
                                                   "manifest_ref": ref("manifest-1",
                                                                       we.MANIFEST_VERSION)})
                self.assertEqual(parsed.evaluation["partition"], partition)
        for partition in ("development", "calibration", "quarantine", "made-up"):
            with self.subTest(partition=partition):
                self.refusal("unknown-value", dc.parse_proposal,
                             proposal_payload(evaluation={"endpoint": "accepted-recovery",
                                                          "partition": partition,
                                                          "manifest_ref": ref(
                                                              "manifest-1",
                                                              we.MANIFEST_VERSION)}))

    def test_the_evidence_partitions_are_exactly_the_owners_held_out_ones(self):
        # The workbench owns the four partitions and their roles; this contract names the subset
        # a proposal may cite. Derived from its table rather than copied, so a role change there
        # cannot leave a fitting partition quietly citable here.
        self.assertTrue(we.PARTITION_ROLES, "the owner's table is what this test derives from")
        held_out = sorted(name for name, role in we.PARTITION_ROLES.items() if role["held_out"])
        self.assertEqual(sorted(dc.EVIDENCE_PARTITIONS), held_out)
        fitting = sorted(name for name, role in we.PARTITION_ROLES.items() if role["fitting"])
        self.assertTrue(fitting, "there is at least one fitting partition to exclude")
        self.assertEqual(sorted(set(dc.EVIDENCE_PARTITIONS) & set(fitting)), [])

    def test_a_proposal_pins_the_exact_parent_it_was_written_against(self):
        self.refusal("not-a-reference", dc.parse_proposal, proposal_payload(parent=None))
        self.refusal("value-invalid", dc.parse_proposal,
                     proposal_payload(parent=al.make_ref("bundle-recovery-context-1",
                                                         version=dc.BUNDLE_VERSION)))
        self.refusal("unknown-value", dc.parse_proposal,
                     proposal_payload(parent=ref("bundle-recovery-context-1",
                                                 dc.CANDIDATE_VERSION)))
        self.assertEqual(self.proposal().parent["v"], dc.BUNDLE_VERSION)

    # ---- the bundle's own internal consistency ------------------------------------------------

    def test_a_bundle_requiring_a_provider_pins_the_contract_it_speaks_to_it_with(self):
        self.refusal("missing-field", dc.parse_bundle,
                     bundle_payload(requirements={"capabilities": [],
                                                  "providers": ["shadow-advisor"],
                                                  "calibration": None}))
        ok = self.bundle(requirements={"capabilities": [], "providers": ["shadow-advisor"],
                                       "calibration": None},
                         components={"decision_contract": dc.CONTRACT_VERSION,
                                     "task_contract": kc.CONTRACT_VERSION,
                                     "provider_contract": "polytropos.provider/1"})
        self.assertEqual(ok.requirements["providers"], ("shadow-advisor",))
        # An offline bundle requires no provider and pins no provider contract: that is V1.
        self.assertIsNone(self.bundle().components["provider_contract"])

    def test_an_approval_with_no_evaluation_behind_it_is_refused(self):
        self.refusal("missing-field", dc.parse_bundle,
                     bundle_payload(provenance={"approval_ref": ref("approval-1", APPROVAL_V),
                                                "evaluation_ref": None,
                                                "rolled_back_from": None}))
        # The reverse is fine: evaluated and not yet approved is a real state.
        parsed = self.bundle(provenance={"approval_ref": None,
                                         "evaluation_ref": ref("manifest-1",
                                                               we.MANIFEST_VERSION),
                                         "rolled_back_from": None})
        self.assertIsNone(parsed.provenance["approval_ref"])

    def test_a_bundle_is_never_its_own_parent_fallback_or_rollback_source(self):
        own = ref("bundle-recovery-context-1", dc.BUNDLE_VERSION)
        self.refusal("value-invalid", dc.parse_bundle, bundle_payload(parent=own))
        self.refusal("value-invalid", dc.parse_bundle,
                     bundle_payload(fallback={"kind": "bundle", "bundle_ref": own}))
        self.refusal("value-invalid", dc.parse_bundle,
                     bundle_payload(provenance={"approval_ref": ref("approval-1", APPROVAL_V),
                                                "evaluation_ref": ref("manifest-1",
                                                                      we.MANIFEST_VERSION),
                                                "rolled_back_from": own}))
        # A root bundle has no parent at all, which is a different thing from pointing at itself.
        self.assertIsNone(self.bundle(parent=None).parent)

    def test_a_scope_is_enumerated_and_is_never_empty_or_wildcarded(self):
        for name, scope in (("no task class", {"project": PROJECT, "task_classes": [],
                                               "intended_uses": [USE]}),
                            ("no use", {"project": PROJECT, "task_classes": [TASK_CLASS],
                                        "intended_uses": []})):
            with self.subTest(scope=name):
                self.refusal("bounds-exceeded", dc.parse_bundle, bundle_payload(scope=scope))
        self.refusal("unknown-value", dc.parse_bundle,
                     bundle_payload(scope={"project": PROJECT, "task_classes": [TASK_CLASS],
                                           "intended_uses": ["act"]}))
        self.refusal("duplicate-entry", dc.parse_bundle,
                     bundle_payload(scope={"project": PROJECT,
                                           "task_classes": [TASK_CLASS, TASK_CLASS],
                                           "intended_uses": [USE]}))
        # Every intended use is one the decision contract already declares, and there is no
        # token meaning "all of them".
        self.assertTrue(dc.INTENDED_USES, "the uses are what a scope is checked against")
        for use in dc.INTENDED_USES:
            with self.subTest(use=use):
                parsed = self.bundle(scope={"project": PROJECT, "task_classes": [TASK_CLASS],
                                            "intended_uses": [use]})
                self.assertEqual(parsed.scope["intended_uses"], (use,))

    def test_a_component_version_is_a_version_and_the_two_that_matter_are_never_unknown(self):
        for key in ("decision_contract", "task_contract"):
            with self.subTest(component=key):
                components = {"decision_contract": dc.CONTRACT_VERSION,
                              "task_contract": kc.CONTRACT_VERSION, "provider_contract": None}
                components[key] = None
                self.refusal("missing-field", dc.parse_bundle,
                             bundle_payload(components=components))
        self.refusal("value-invalid", dc.parse_bundle,
                     bundle_payload(components={"decision_contract": "has spaces/1",
                                                "task_contract": kc.CONTRACT_VERSION,
                                                "provider_contract": None}))
        self.refusal("wrong-type", dc.parse_bundle,
                     bundle_payload(components={"decision_contract": 1,
                                                "task_contract": kc.CONTRACT_VERSION,
                                                "provider_contract": None}))
        # A version carries a '/' that an identifier may not, which is why it has its own check.
        self.assertIn("/", dc.CONTRACT_VERSION)
        self.refusal("value-invalid", dc.parse_bundle, bundle_payload(id=dc.CONTRACT_VERSION))

    # ---- the historical shape -----------------------------------------------------------------

    def test_the_historical_preference_shape_loads_and_is_still_not_a_bundle(self):
        payload = preference_payload()
        self.assertTrue(dc.is_legacy_preference_payload(payload))
        self.assertFalse(dc.is_legacy_preference_payload(bundle_payload()))
        self.assertFalse(dc.is_legacy_preference_payload(None))
        # Refused BY NAME, so a caller can tell the old shape from a malformed payload without
        # reading a message -- and the message says which shape it is, not just that v is wrong.
        refusal = self.refusal("unknown-value", dc.parse_bundle, payload)
        self.assertIn("preference payload", str(refusal))
        self.assertIn(dc.LEGACY_PREFERENCE_VERSION, str(refusal))
        # And it LOADS: read for what it is, with its own keys reported as unmapped rather than
        # translated into approved parameters.
        view = dp.describe_legacy_preferences(payload)
        self.assertEqual(view.version, we.POLICY_VERSION)
        self.assertEqual(view.policy_version, 3)
        self.assertEqual(dict(view.defaults), {"workflow": "kit"})
        self.assertEqual(view.unmapped, ("policy", "workflow"))
        self.assertEqual(view.reasons, (dp.LEGACY_PREFERENCE_REASON,))
        self.assertEqual([f.name for f in dataclasses.fields(view)],
                         ["version", "policy_version", "defaults", "by_task_class",
                          "unmapped", "reasons"])
        # No digest, no reference, no scope: there is nothing on this view to pin a run to.
        self.assertFalse(hasattr(view, "sha"))
        self.assertFalse(hasattr(view, "parameters"))

    def test_the_historical_preference_version_is_the_one_its_owner_writes(self):
        # Declared in the contract so a bundle parser can refuse that shape by name, and pinned
        # here against the workbench's own constant so the two cannot drift apart. Nothing in
        # `bin/` reads that file except its owner, and this contract never locates it.
        self.assertEqual(dc.LEGACY_PREFERENCE_VERSION, we.POLICY_VERSION)
        self.assertNotEqual(dc.LEGACY_PREFERENCE_VERSION, dc.BUNDLE_VERSION)
        self.assertNotIn(we.POLICY_FILE, POLICY_PATH.read_text(encoding="utf-8"))
        self.assertNotIn(we.POLICY_FILE, CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_a_preference_payload_in_the_catalog_never_resolves_as_a_bundle(self):
        # Even hand-edited to carry an id a pin could name, it does not parse as a bundle, so
        # resolution reports it and stays legacy.
        disguised = preference_payload(id="bundle-recovery-context-1")
        resolution = dp.resolve_bundle(ref("bundle-recovery-context-1", dc.BUNDLE_VERSION),
                                       [disguised], self.facts())
        self.assertEqual(resolution.source, "legacy")
        self.assertEqual(resolution.reasons, ("bundle-invalid",))
        self.assertIsNone(resolution.bundle)
        # And with no id at all it is not even reachable by a pin.
        plain = dp.resolve_bundle(ref("bundle-recovery-context-1", dc.BUNDLE_VERSION),
                                  [preference_payload()], self.facts())
        self.assertEqual(plain.reasons, ("bundle-unknown",))
        self.assertRaises(dc.ContractError, dp.describe_legacy_preferences, bundle_payload())

    def test_a_bundle_pinning_an_older_component_version_still_loads(self):
        # Backward compatibility means the record READS. Whether it applies is resolution's
        # question, and the answer is the legacy behaviour rather than a parse failure.
        historical = bundle_payload(components={"decision_contract": "polytropos.decision/0",
                                                "task_contract": "polytropos.kit/0",
                                                "provider_contract": None})
        parsed = dc.parse_bundle(historical)
        self.assertEqual(parsed.components["decision_contract"], "polytropos.decision/0")
        self.assertEqual(parsed.sha(), dc.parse_bundle(parsed.to_payload()).sha())
        resolution = self.resolve([historical])
        self.assertEqual(resolution.source, "legacy")
        self.assertIn("component-mismatch", resolution.reasons)

    # ---- a bundle grants nothing ---------------------------------------------------------------

    def test_a_resolution_carries_no_mode_no_grant_and_no_permission(self):
        names = [f.name for f in dataclasses.fields(dp.BundleResolution)]
        self.assertEqual(names, ["source", "bundle", "ref", "chain", "reasons"])
        self.assertTrue(dc.BANNED_FIELDS, "an empty ban would make the sweep below vacuous")
        self.assertEqual(sorted(n for n in names if dc._is_banned_key(n)), [])
        resolution = self.resolve([bundle_payload()])
        # Nothing on a selected resolution says what may now be done, and in particular no mode:
        # legacy stays the runtime's mode until a separately gated transition says otherwise.
        for absent in ("mode", "approved", "permissions", "budget", "activate"):
            with self.subTest(attribute=absent):
                self.assertFalse(hasattr(resolution, absent))
        self.assertEqual(sorted(dict(resolution.parameters)),
                         sorted(bundle_payload()["parameters"]))
        # The vocabularies are closed at construction, so an undeclared one cannot be built.
        # `source="active"` is paired with a BUNDLE here on purpose: paired with None it would
        # also break the coherence check below, and that check would then be what refuses it.
        self.assertRaises(dc.ContractError, dp.BundleResolution,
                          source="active", bundle=resolution.bundle, ref=None, chain=(),
                          reasons=("selected",))
        self.assertRaises(dc.ContractError, dp.BundleResolution,
                          source="legacy", bundle=None, ref=None, chain=(),
                          reasons=("promoted",))
        self.assertRaises(dc.ContractError, dp.BundleResolution,
                          source="legacy", bundle=resolution.bundle, ref=None, chain=(),
                          reasons=("selected",))

    def test_the_policy_module_writes_nothing_and_starts_nothing(self):
        text = POLICY_PATH.read_text(encoding="utf-8")
        tree = ast.parse(text)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])
        # Without this guard a module reaching every import dynamically would pass the two
        # checks below on an empty set -- the vacuous-AST-guard hole D09 shipped four of.
        self.assertTrue(imported, "the AST walk found no imports at all")
        self.assertTrue(imported <= set(sys.stdlib_module_names), sorted(imported))
        for forbidden in ("subprocess", "socket", "urllib", "http", "ssl", "shutil", "os"):
            with self.subTest(module=forbidden):
                self.assertNotIn(forbidden, imported)
        calls = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Attribute):
                    calls.add(fn.attr)
                elif isinstance(fn, ast.Name):
                    calls.add(fn.id)
        self.assertTrue(calls, "the AST walk found no calls, so the sweep below is vacuous")
        self.assertIn("parse_bundle", calls, "the walk reaches the code that matters")
        for writer in ("open", "write_text", "write_bytes", "mkdir", "replace", "unlink",
                       "rename", "rmtree", "touch", "system", "run", "Popen"):
            with self.subTest(call=writer):
                self.assertNotIn(writer, calls)
        for pattern in ("subprocess.", "Path.home(", "os.environ"):
            with self.subTest(pattern=pattern):
                self.assertNotIn(pattern, text)

    def test_the_policy_module_reaches_for_no_private_name_of_the_contract(self):
        # `decision_contract` already reaches two private helpers of `attempt_history`, which is
        # recorded as a smell; this module does not add a third case. Everything it needs from
        # the contract is public, so a refactor there breaks a name rather than a behaviour.
        tree = ast.parse(POLICY_PATH.read_text(encoding="utf-8"))
        public, private = set(), set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            value = node.value
            direct = (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                      and value.func.id == "_contract")
            bound = isinstance(value, ast.Name) and value.id == "contract"
            if direct or bound:
                (private if node.attr.startswith("_") else public).add(node.attr)
        self.assertTrue(public, "the walk found no contract access at all")
        self.assertIn("parse_bundle", public)
        self.assertEqual(sorted(private), [])

    def test_every_refusal_and_every_reason_this_module_uses_is_a_declared_one(self):
        tree = ast.parse(POLICY_PATH.read_text(encoding="utf-8"))
        raised, produced = set(), set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "_refuse"):
                self.assertTrue(node.args, "a refusal always names its reason code first")
                self.assertIsInstance(node.args[0], ast.Constant, ast.dump(node.args[0]))
                raised.add(node.args[0].value)
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "append" and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "reasons" and node.args
                    and isinstance(node.args[0], ast.Constant)):
                produced.add(node.args[0].value)
            if isinstance(node, ast.keyword) and node.arg == "reasons":
                if isinstance(node.value, ast.Tuple):
                    produced.update(e.value for e in node.value.elts
                                    if isinstance(e, ast.Constant))
        self.assertTrue(raised, "the walk found no refusals")
        self.assertEqual(sorted(raised - set(dc.REASON_CODES)), [])
        # Both directions: no reason is produced that is not declared, and no reason is declared
        # that nothing produces. A dead code in the vocabulary is a branch somebody removed.
        self.assertEqual(sorted(produced), sorted(dp.RESOLUTION_REASONS))
        self.assertEqual(list(dp.RESOLUTION_REASONS), sorted(set(dp.RESOLUTION_REASONS)))

    def test_the_named_argument_form_refuses_what_the_dict_form_refuses(self):
        # `_runtime` already refused `capabilities="dispatch"` (the test below asserts it), but
        # `runtime_facts` used to write `list(capabilities)` before handing over, so the guard
        # was unreachable through the public door: one capability id passed unwrapped became
        # twenty-one single-character capabilities, and `dict(components)` turned a list of
        # two-character strings into a dict of their letters. A convenience wrapper that coerces
        # first answers the question before the validator can ask it. These cases go through
        # `runtime_facts`, not `_runtime`, because that is where the coercion was.
        base = {"project": PROJECT, "task_class": TASK_CLASS, "intended_use": USE,
                "components": {}, "capabilities": (), "providers": (), "calibration": None}
        for key in ("capabilities", "providers"):
            with self.subTest(field=key):
                self.refusal("wrong-type", lambda **kw: dp.runtime_facts(**kw),
                             **dict(base, **{key: "codex-native-dispatch"}))
        self.refusal("wrong-type", lambda **kw: dp.runtime_facts(**kw),
                     **dict(base, components=["ab", "cd"]))
        # The correct call is unaffected: one id in a list stays one id, not its letters.
        self.assertEqual(
            dp.runtime_facts(**dict(base, capabilities=["codex-native-dispatch"]))["capabilities"],
            ("codex-native-dispatch",))

    def test_the_runtime_facts_are_closed_and_an_unestablished_fact_is_written_as_one(self):
        base = {"project": PROJECT, "task_class": TASK_CLASS, "intended_use": USE,
                "components": {}, "capabilities": [], "providers": [], "calibration": None}
        self.assertEqual(dp._runtime(base)["capabilities"], ())
        self.refusal("unknown-field", dp._runtime, dict(base, mode="active"))
        for key in dp.RUNTIME_KEYS:
            with self.subTest(missing=key):
                self.refusal("missing-field", dp._runtime,
                             {k: v for k, v in base.items() if k != key})
        self.refusal("wrong-type", dp._runtime, "facts")
        self.refusal("value-invalid", dp._runtime, dict(base, project=""))
        self.refusal("unknown-value", dp._runtime, dict(base, intended_use="act"))
        self.refusal("unknown-field", dp._runtime,
                     dict(base, components={"pricing": "x"}))
        self.refusal("wrong-type", dp._runtime, dict(base, capabilities="dispatch"))
        self.refusal("value-invalid", dp._runtime, dict(base, providers=[1]))
        self.refusal("not-a-reference", dp._runtime, dict(base, calibration="calib-1"))
        # A caller defect raises rather than degrading to legacy, which would hide the bug.
        self.refusal("unknown-field", dp.resolve_bundle, None, [bundle_payload()],
                     dict(base, mode="active"))
        # The facts a caller already validated are accepted again unchanged, so passing a
        # resolution's own facts back in is not a second, different validation.
        self.assertEqual(dp.resolve_bundle(None, [], dp._runtime(base)).reasons, ("no-pin",))
        # A catalog that is not a sequence at all is refused as one, rather than left to blow up
        # on iteration -- which is the only case the per-entry check below cannot also catch,
        # and therefore the only case that isolates the whole-catalog check.
        self.refusal("wrong-type", dp.resolve_bundle, None, 5, self.facts())
        whole = self.refusal("wrong-type", dp.resolve_bundle, None, {"a": 1}, self.facts())
        self.assertIn("must be a list", str(whole))
        entry = self.refusal("wrong-type", dp.resolve_bundle, None, ["not a payload"],
                             self.facts())
        self.assertIn("catalog[0]", str(entry))

    def test_resolution_is_payload_shaped_so_a_second_loader_cannot_break_it(self):
        # `bin/` is not a package: two loaders of one file produce two class objects, and an
        # `isinstance` across that boundary is false. This kit has already been bitten by it.
        other = _load("decision_contract")
        self.assertIsNot(other.PolicyBundle, dc.PolicyBundle)
        self.assertEqual(other.BUNDLE_VERSION, dc.BUNDLE_VERSION)
        foreign = other.parse_bundle(bundle_payload())
        # A digest is a property of content, not of whoever parsed it, so the reference matches.
        self.assertEqual(dp.bundle_ref(foreign), dp.bundle_ref(bundle_payload()))
        resolution = dp.resolve_bundle(dp.bundle_ref(foreign), [bundle_payload()], self.facts())
        self.assertEqual(resolution.source, "pinned")
        self.assertIsInstance(resolution.bundle, dc.PolicyBundle)
        self.assertNotIsInstance(resolution.bundle, other.PolicyBundle)

    def test_the_two_records_are_frozen_and_their_maps_are_not_writable(self):
        bundle = self.bundle()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            bundle.id = "something-else"
        for name in ("scope", "components", "parameters", "requirements", "fallback",
                     "provenance"):
            with self.subTest(field=name):
                with self.assertRaises(TypeError):
                    getattr(bundle, name)["injected"] = True
        proposal = self.proposal()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            proposal.hypothesis = "something else"
        with self.assertRaises(TypeError):
            proposal.diff["injected"] = True


if __name__ == "__main__":
    unittest.main()
