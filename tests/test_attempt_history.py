"""Step 17: bin/attempt_history.py -- one record shape over the ledger, NOTES.md and role-use.

What these establish: history is never collapsed (a failed run and its passing rerun are both
records, and `latest_state` is a separate projection); a failed consult keeps its parent; an
unknown model stays unknown and is counted as such; a review seen by both the ledger and
Codex's typed record is one record; cost bases are kept apart; and the join is idempotent.

Everything reads temp fixtures through an injected registry with fixture ids. No real store,
no real pricing, no real home.
"""

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ah = _load("attempt_history")
al = _load("attempt_ledger")
mr = _load("model_registry")
kc = _load("kit_contract")

_DATA_HOME = None
_DATA_HOME_PATCH = None


def setUpModule():
    global _DATA_HOME, _DATA_HOME_PATCH
    _DATA_HOME = tempfile.TemporaryDirectory(prefix="polytropos-test-data-")
    _DATA_HOME_PATCH = mock.patch.dict(os.environ, {"POLYTROPOS_DATA_HOME": _DATA_HOME.name})
    _DATA_HOME_PATCH.start()


def tearDownModule():
    _DATA_HOME_PATCH.stop()
    _DATA_HOME.cleanup()


BUNDLE = {
    "claude": {"cached_date": "2020-01-01", "models": {
        "fake-opus": {"tier": "opus"}, "fake-fable": {"tier": "frontier"}}},
    "codex": {"cached_date": "2020-02-02", "models": {
        "fake-sol": {"tier": "strong"}, "fake-astra": {"tier": "frontier"}}},
    "copilot": {"cached_date": "2020-03-03", "models": {"fake-terra": {"tier": "mid"}}},
}

TASKS_MD = """# TASKS

## Phase 1 — demo

### T1 — First
- status: done
- model: fake-opus

**Brief.** x

**Verify.**
```bash
true
```

### T2 — Second
- status: blocked
- model: fake-fable

**Brief.** x

**Verify.**
```bash
true
```
"""


class _Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.kits = self.root / "kits"
        self.store = self.root / "store"
        self.reg = mr.Registry(pricing_bundle=BUNDLE)

    def tearDown(self):
        self._tmp.cleanup()

    def kit(self, name, notes="", role_use=None):
        d = self.kits / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "TASKS.md").write_text(TASKS_MD)
        if notes:
            (d / "NOTES.md").write_text(notes)
        if role_use:
            (d / "role-use.jsonl").write_text(
                "".join(json.dumps(r) + "\n" for r in role_use))
        return d

    def ledger(self, name):
        return al.AttemptLedger(self.store, name)

    def join(self):
        return ah.join_kits(self.kits, store=self.store, registry=self.reg)


class HistoryIsNeverCollapsedTests(_Fixture):
    def test_a_failed_run_and_its_passing_rerun_are_both_records(self):
        self.kit("alpha", notes=(
            "## 2026-01-01T00:00:00Z — T1\n- role: implementer\n"
            "- outcome: T1 model=fake-opus attempts=2 result=blocked review=none run=r1\n\n"
            "## 2026-01-02T00:00:00Z — T1\n- role: implementer\n"
            "- outcome: T1 model=fake-opus attempts=1 result=pass review=none run=r2\n"))
        records, _notes, _cov = self.join()
        t1 = [r for r in records if r["task"] == "T1"]
        self.assertEqual([r["result"] for r in t1], ["blocked", "pass"])
        self.assertEqual(ah.latest_state(records)["alpha/T1"]["result"], "pass")

    def test_a_budget_stop_never_supersedes_a_verdict_in_the_projection(self):
        self.kit("alpha", notes=(
            "## a — T1\n- outcome: T1 model=fake-opus attempts=1 result=blocked review=none run=r1\n\n"
            "## b — T1\n- outcome: T1 model=fake-opus attempts=0 result=budget-stop review=none run=r2\n"))
        records, _n, _c = self.join()
        self.assertEqual(len([r for r in records if r["task"] == "T1"]), 2)
        self.assertEqual(ah.latest_state(records)["alpha/T1"]["result"], "blocked")

    def test_every_record_carries_every_field_and_names_what_was_observed(self):
        self.kit("alpha", notes="## a — T1\n- outcome: T1 model=fake-opus attempts=1 result=pass review=none\n")
        records, _n, _c = self.join()
        rec = records[0]
        self.assertEqual(set(rec), set(ah.RECORD_FIELDS))
        self.assertIn("dispatched_model", rec["observed"])
        self.assertNotIn("observed_model", rec["observed"])
        self.assertIsNone(rec["observed_model"])
        with self.assertRaises(KeyError):
            ah.observe(ah.blank(), not_a_field=1)


class LineageTests(_Fixture):
    def test_a_failed_consult_keeps_its_parent_from_the_ledger(self):
        self.kit("alpha")
        ledger = self.ledger("alpha")
        ledger.append("run.started", run="r3", task="T2", actor="claude-code", pid=1)
        a = ledger.record_started("r3", "T2", "consult", "fake-fable", parent="T1",
                                  role="implementer", actor="claude-code")
        ledger.record_finished("r3", "T2", a, "failed", 1, "Not logged in", cls="auth")
        records, _n, _c = self.join()
        chains = ah.lineage(records)
        self.assertEqual(len(chains), 1)
        self.assertEqual(chains[0]["parent"], "T1")
        self.assertEqual(chains[0]["verdict"], "unrescued")
        self.assertEqual(chains[0]["children"][0]["result"], "dispatch-failed")

    def test_a_rescue_is_charged_to_the_whole_chain(self):
        self.kit("alpha", notes=(
            "## a — T1\n- role: implementer\n"
            "- outcome: T1 model=fake-opus attempts=3 result=blocked review=none run=r1\n\n"
            "## b — T2\n- role: implementer\n"
            "- outcome: T2 model=fake-fable attempts=1 result=escalated-pass review=none "
            "run=r2 parent=T1\n"))
        records, _n, _c = self.join()
        chain = ah.lineage(records)[0]
        self.assertEqual(chain["verdict"], "rescued")
        self.assertEqual(chain["attempts"], 4, "the cheap pin's three failures are part of the cost")


class UnknownStaysUnknownTests(_Fixture):
    def test_an_unknown_model_has_no_tier_and_is_counted(self):
        self.kit("alpha", notes="## a — T1\n- outcome: T1 model=mystery-9 attempts=1 result=pass review=none\n")
        records, notes, cov = self.join()
        self.assertIsNone(records[0]["tier"])
        card = ah.summarize(records, notes, cov, registry=self.reg)
        self.assertEqual(card["unknown"]["tier"], 1)
        self.assertIn("unknown", card["by_harness"])

    def test_a_notes_line_takes_its_harness_from_the_ledger_run_it_projects(self):
        self.kit("alpha", notes=(
            "## a — T1\n- role: implementer\n"
            "- outcome: T1 model=fake-opus attempts=1 result=pass review=none run=r1\n"))
        ledger = self.ledger("alpha")
        ledger.append("run.started", run="r1", task="T1", actor="claude-code", pid=1)
        a = ledger.record_started("r1", "T1", "initial", "fake-opus", actor="claude-code")
        ledger.record_finished("r1", "T1", a, "ok", 0, "x")
        ledger.record_verify("r1", "T1", a, 0, "ok")
        records, _n, _c = self.join()
        line = [r for r in records if r["source"] == "notes"][0]
        self.assertEqual(line["harness"], "claude")
        self.assertIn("harness:from-ledger-run", line["observed"])
        self.assertEqual(line["ledger_attempts"], [a])

    def test_a_disagreement_between_the_line_and_the_ledger_is_noted_and_both_kept(self):
        self.kit("alpha", notes=(
            "## a — T1\n- outcome: T1 model=fake-opus attempts=5 result=pass review=none run=r1\n"))
        ledger = self.ledger("alpha")
        a = ledger.record_started("r1", "T1", "initial", "fake-opus", actor="claude-code")
        ledger.record_finished("r1", "T1", a, "ok", 0, "x")
        records, notes, _c = self.join()
        self.assertEqual(len(records), 2)
        self.assertTrue(any("attempts=5" in n and "ledger holds 1" in n for n in notes))


class RoleJoinTests(_Fixture):
    ROLE_USE = {"schema": "polytropos.role-use/1", "recorded_at": "2026-01-05T00:00:00Z",
                "phase": "1", "role": "verifier", "run_id": "g1", "attempt": 1,
                "dispatch_rc": 0, "planned_model": None, "dispatched_model": "fake-sol",
                "actual_model": "fake-sol", "actual_role": "verifier", "result": None,
                "evidence_fingerprint": "fp", "report_sha256": "d"}

    def test_a_typed_review_record_and_its_ledger_twin_are_one_record(self):
        kit = self.kit("gamma", role_use=[self.ROLE_USE])
        kc.record_role_dispatch(kit, "g1", "verifier", "1", "fake-sol", 0, "fine",
                                actor="codex", store=self.store)
        records, _n, _c = self.join()
        reviews = [r for r in records if r["op"] == "review"]
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0]["source"], "ledger+role-use")
        self.assertEqual(reviews[0]["observed_model"], "fake-sol")
        self.assertEqual(reviews[0]["harness"], "codex")
        self.assertEqual(reviews[0]["tier"], "strong")

    def test_a_typed_record_with_no_ledger_twin_is_still_a_record(self):
        self.kit("gamma", role_use=[self.ROLE_USE])
        records, _n, _c = self.join()
        self.assertEqual([r["source"] for r in records if r["op"] == "review"], ["role-use"])

    def test_a_claude_review_recorded_by_the_driver_appears_with_its_phase(self):
        kit = self.kit("alpha")
        kc.record_role_dispatch(kit, "c1", "reviewer", "2", None, 0, "ok", actor="claude-code",
                                store=self.store)
        records, _n, _c = self.join()
        rev = [r for r in records if r["op"] == "review"][0]
        self.assertEqual((rev["harness"], rev["phase"], rev["task"]), ("claude", "2", "phase-2"))


class CostBasesTests(_Fixture):
    def test_bases_are_kept_apart_and_never_summed(self):
        self.kit("beta", notes=(
            "## a — T1\n- agent: implementer\n"
            "- budget: standard=x actual=fake-terra profile=S est_standard_usd=0.0400 "
            "est_actual_usd=0.0100 delta_usd=-0.0300 status=done\n"
            "- outcome: T1 model=fake-terra attempts=1 result=pass review=none run=c1\n"))
        ledger = self.ledger("alpha")
        self.kit("alpha")
        a = ledger.record_started("r1", "goal", "tick", "fake-opus", actor="ralph")
        ledger.record_finished("r1", "goal", a, "ok", 0, "x", cost_usd=0.5, cost_source="parsed")
        b = ledger.record_started("r1", "goal", "tick", "fake-opus", actor="ralph")
        ledger.record_finished("r1", "goal", b, "ok", 0, "x", cost_usd=0.25,
                               cost_source="estimated")
        records, _n, _c = self.join()
        totals = ah.cost_totals(records)
        by = totals["by_basis"]
        self.assertEqual(by["estimated"]["n"], 2)
        self.assertAlmostEqual(by["estimated"]["usd"], 0.26)
        self.assertEqual(by["model-reported"]["n"], 1)
        self.assertAlmostEqual(by["model-reported"]["usd"], 0.5)
        self.assertEqual(by["billed"]["n"], 0)
        self.assertIsNone(by["billed"]["usd"])
        self.assertNotIn("total", totals)
        self.assertEqual(totals["records_with_cost"], 3)


class JoinPropertiesTests(_Fixture):
    def test_joining_twice_yields_the_same_records_with_no_duplicates(self):
        self.kit("alpha", notes="## a — T1\n- outcome: T1 model=fake-opus attempts=1 result=pass review=none run=r1\n")
        ledger = self.ledger("alpha")
        a = ledger.record_started("r1", "T1", "initial", "fake-opus", actor="claude-code")
        ledger.record_finished("r1", "T1", a, "ok", 0, "x")
        first, _n1, _c1 = self.join()
        second, _n2, _c2 = self.join()
        self.assertEqual(first, second)
        keys = [(r["kit"], r["source"], r["attempt"]) for r in first]
        self.assertEqual(len(keys), len(set(keys)))

    def test_coverage_counts_what_each_kit_actually_has(self):
        self.kit("alpha", notes="## a — T1\n- outcome: T1 model=fake-opus attempts=1 result=pass review=none\n")
        self.kit("beta")
        self.ledger("beta").record_started("r1", "T1", "initial", "fake-terra", actor="copilot")
        _r, _n, cov = self.join()
        self.assertEqual(cov, {"kits": 2, "kits_with_ledger": 1, "kits_with_notes": 1,
                               "kits_with_role_use": 0})

    def test_show_and_demo_render_and_touch_no_real_store(self):
        self.kit("alpha", notes="## a — T1\n- outcome: T1 model=fake-opus attempts=1 result=pass review=none\n")
        before = set(Path(_DATA_HOME.name).rglob("*"))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ah._cli(["show", "--kits-dir", str(self.kits), "--attempt-store",
                          str(self.store), "--json"])
        self.assertEqual(rc, 0)
        card = json.loads(buf.getvalue())
        self.assertEqual(card["schema"], ah.HISTORY_VERSION)
        self.assertEqual(card["records"], 1)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(ah._cli(["demo"]), 0)
        self.assertIn("Attempt history", buf.getvalue())
        self.assertEqual(before, set(Path(_DATA_HOME.name).rglob("*")))


if __name__ == "__main__":
    unittest.main()
