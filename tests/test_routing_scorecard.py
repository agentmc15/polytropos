"""Stdlib unittest regression suite for bin/routing_scorecard.py (fusion-tier1 T6).

SAFETY CONTRACT (binds every test in this file): no test here ever reads the real Claude
Code project store or resolves the caller's real home directory via the stdlib Path.home
helper -- this file never calls it, and it never spells out the real projects path as a
literal string. Every kit fixture (TASKS.md / NOTES.md) is written into a fresh
`tempfile.TemporaryDirectory()` and handed to the CLI or the pure functions via an
explicit `--kits-dir` / kit path — never a bare slug against the real
`.claude/kits`. Every transcript fixture lives under a temp `--projects-dir`, and
every CLI invocation that passes `--session` also passes `--projects-dir` and
`--no-subagents` explicitly. The pricing dict `P` used by the direct (non-subprocess)
unit tests below is a SYNTHETIC module constant -- fake ids, round rates, no
`intro_pricing`; the real `data/pricing.json` is opened only indirectly, read-only, by
the subprocess-driven CLI end-to-end tests (routing_scorecard.py has no pricing-file
override flag, so any subprocess invocation of it -- demo or not -- loads the real
pricing file itself; this file never asserts a real price or a real model id from it).

bin/ is not a package; routing_scorecard.py is loaded via importlib by absolute path
computed from this file's own location (BIN_DIR), mirroring tests/test_session_cost.py
and tests/test_journal_sources.py.
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"
REPO_ROOT = BIN_DIR.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rs = _load("routing_scorecard")


# ---- synthetic pricing fixture ---------------------------------------------------------------
#
# Fake ids, round rates, frontier the priciest tier, NO intro_pricing (so every price below
# is the base rate, never a time-gated intro rate).

P = {
    "cached_date": "2020-01-01",
    "billing_mode": "api",
    "cache_read_multiplier": 0.1,
    "cache_write_multiplier_5m": 1.25,
    "models": {
        "fake-haiku-1": {
            "display": "Fake Haiku", "tier": "haiku",
            "input_per_mtok": 1.0, "output_per_mtok": 5.0,
        },
        "fake-sonnet-1": {
            "display": "Fake Sonnet", "tier": "sonnet",
            "input_per_mtok": 3.0, "output_per_mtok": 15.0,
        },
        "fake-frontier-1": {
            "display": "Fake Frontier", "tier": "frontier",
            "input_per_mtok": 15.0, "output_per_mtok": 75.0,
        },
    },
}

# Custom expensive-tier set used by the pure-function unit tests below (frontier/opus,
# matching cost_report.EXPENSIVE_TIERS structurally -- but a plain module constant here,
# never imported from cost_report, so is_cheap's parametrization is genuinely exercised).
EXP = {"frontier", "opus"}


# ---- fixture helpers --------------------------------------------------------------------------

def _task(tid, title="a task", status="done", model=None):
    """A dict matching copilot_execute.parse_tasks output shape, for build_scorecard tests
    that want fine control over a task's model field (including None)."""
    return {
        "id": tid, "title": title, "status": status, "model": model,
        "depends": [], "independent": False, "brief": "", "verify": None,
    }


def _line(model, mid, ts="2020-06-01T00:00:00Z", inp=0, out=0, cache_read=0, cache_write=0):
    """One Claude Code transcript JSONL line (session_cost.py's expected shape)."""
    return json.dumps({
        "timestamp": ts,
        "message": {
            "id": mid,
            "model": model,
            "usage": {
                "input_tokens": inp,
                "output_tokens": out,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_write,
            },
        },
    })


def _write_kit(kits_root, slug, tasks_md, notes_md=None):
    """Write a temp kit dir: kits_root/slug/TASKS.md (+ optional NOTES.md). Returns the dir."""
    kit_dir = Path(kits_root) / slug
    kit_dir.mkdir(parents=True)
    (kit_dir / "TASKS.md").write_text(tasks_md)
    if notes_md is not None:
        (kit_dir / "NOTES.md").write_text(notes_md)
    return kit_dir


def _run_cli(args):
    """subprocess.run the real CLI from the repo root (never the dotted-module form)."""
    return subprocess.run(
        [sys.executable, "bin/routing_scorecard.py"] + args,
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )


# TASKS.md / NOTES.md fixtures for the CLI end-to-end section. The em dash below is the
# literal U+2014 spaced separator copilot_execute.parse_tasks requires in task headings.
CLI_TASKS_MD = """# TASKS — cli-e2e (synthetic test fixture)

## Phase 1 — only phase

### E1 — first task
- status: done
- model: haiku

### E2 — second task
- status: done
- model: sonnet

### E3 — third task
- status: blocked
- model: sonnet
"""

CLI_NOTES_MD = """# NOTES — cli-e2e (synthetic test fixture)

## Outcome ledger
outcome: E1 model=haiku attempts=1 result=pass review=clean
outcome: E2 model=sonnet attempts=2 result=retry-pass review=revised
outcome: E3 model=sonnet attempts=2 result=blocked review=none
"""

BAD_STATUS_TASKS_MD = """# TASKS — bad-kit (synthetic test fixture)

## Phase 1 — only phase

### B1 — broken task
- status: not-a-real-status
- model: haiku
"""

# The five pinned D10 markdown H2s, asserted independently of routing_scorecard.MD_H2S so a
# regression in the module's own constant would not silently pass this test.
EXPECTED_H2S = ("## Verdict", "## Task outcomes", "## Model mix", "## Review survival",
                "## Dollars")


# ---- 1. parse_outcomes -------------------------------------------------------------------------


class ParseOutcomesTests(unittest.TestCase):
    def test_happy_path_parses_all_fields(self):
        text = "outcome: A1 model=haiku attempts=2 result=pass review=clean"
        outcomes, notes = rs.parse_outcomes(text)
        self.assertEqual(notes, [])
        self.assertEqual(outcomes, {
            "A1": {"model": "haiku", "attempts": 2, "result": "pass", "review": "clean"},
        })

    def test_last_line_wins_per_id(self):
        text = "\n".join([
            "outcome: A1 model=haiku attempts=1 result=pass review=clean",
            "outcome: A1 model=sonnet attempts=2 result=retry-pass review=revised",
        ])
        outcomes, notes = rs.parse_outcomes(text)
        self.assertEqual(notes, [])
        self.assertEqual(outcomes, {
            "A1": {"model": "sonnet", "attempts": 2, "result": "retry-pass",
                   "review": "revised"},
        })

    def test_leading_dash_and_star_bullets_parse(self):
        text = "\n".join([
            "- outcome: A1 model=haiku attempts=1 result=pass review=clean",
            "* outcome: A2 model=sonnet attempts=1 result=pass review=clean",
        ])
        outcomes, notes = rs.parse_outcomes(text)
        self.assertEqual(notes, [])
        self.assertEqual(set(outcomes), {"A1", "A2"})

    def test_unknown_key_value_pairs_ignored(self):
        text = "outcome: A1 model=haiku attempts=1 result=pass review=clean foo=bar baz=qux"
        outcomes, notes = rs.parse_outcomes(text)
        self.assertEqual(notes, [])
        self.assertEqual(outcomes["A1"], {
            "model": "haiku", "attempts": 1, "result": "pass", "review": "clean",
        })

    def test_missing_model_skips_with_note(self):
        text = "outcome: A1 attempts=1 result=pass review=clean"
        outcomes, notes = rs.parse_outcomes(text)
        self.assertEqual(outcomes, {})
        self.assertTrue(any("unrecognized outcome line" in n for n in notes))

    def test_bad_result_skips_with_note(self):
        text = "outcome: A1 model=haiku attempts=1 result=not-a-real-result review=clean"
        outcomes, notes = rs.parse_outcomes(text)
        self.assertEqual(outcomes, {})
        self.assertTrue(any("unrecognized outcome line" in n for n in notes))

    def test_non_integer_attempts_defaults_to_one_with_note(self):
        text = "outcome: A1 model=haiku attempts=lots result=pass review=clean"
        outcomes, notes = rs.parse_outcomes(text)
        self.assertEqual(outcomes["A1"]["attempts"], 1)
        self.assertTrue(any("non-integer attempts" in n for n in notes))

    def test_bad_review_defaults_to_none_with_note(self):
        text = "outcome: A1 model=haiku attempts=1 result=pass review=whatever"
        outcomes, notes = rs.parse_outcomes(text)
        self.assertEqual(outcomes["A1"]["review"], "none")
        self.assertTrue(any("unknown review" in n for n in notes))

    def test_zero_ledger_notes_md_returns_empty_dict_and_notes(self):
        text = "# NOTES\n\nJust prose describing the run, no ledger lines here at all.\n"
        self.assertEqual(rs.parse_outcomes(text), ({}, []))


# ---- 2. tier_for / is_cheap --------------------------------------------------------------------


class TierForIsCheapTests(unittest.TestCase):
    def test_fable_maps_to_frontier_tier(self):
        self.assertEqual(rs.tier_for("fable"), "frontier")

    def test_other_aliases_are_identity(self):
        for alias in ("haiku", "sonnet", "opus"):
            self.assertEqual(rs.tier_for(alias), alias)

    def test_fable_is_not_cheap(self):
        self.assertFalse(rs.is_cheap("fable", EXP))

    def test_haiku_and_sonnet_are_cheap(self):
        self.assertTrue(rs.is_cheap("haiku", EXP))
        self.assertTrue(rs.is_cheap("sonnet", EXP))

    def test_opus_is_not_cheap(self):
        self.assertFalse(rs.is_cheap("opus", EXP))

    def test_custom_expensive_set_is_honored(self):
        custom = {"sonnet"}
        self.assertFalse(rs.is_cheap("sonnet", custom))
        self.assertTrue(rs.is_cheap("haiku", custom))
        self.assertTrue(rs.is_cheap("opus", custom))  # opus not in this custom set


# ---- 3. build_scorecard -------------------------------------------------------------------------


class BuildScorecardTests(unittest.TestCase):
    def test_replicates_demo_math_key_by_key(self):
        # Independent fixture (own ids, not the module's DEMO_TASKS_MD/DEMO_NOTES_MD) that
        # follows the same one-of-each-result-type shape as the pinned D9 demo numbers, plus
        # one outcome line for an id that is NOT a task (must be noted, not turned into a row).
        tasks = [
            _task("X1", model="haiku"),
            _task("X2", model="sonnet"),
            _task("X3", model="sonnet"),
            _task("X4", model="sonnet"),
            _task("X5", model="fable"),
            _task("X6", model="sonnet", status="blocked"),
        ]
        notes_text = "\n".join([
            "outcome: X1 model=haiku attempts=1 result=pass review=clean",
            "outcome: X2 model=sonnet attempts=1 result=pass review=clean",
            "outcome: X3 model=sonnet attempts=1 result=pass review=revised",
            "outcome: X4 model=sonnet attempts=2 result=retry-pass review=clean",
            "outcome: X5 model=fable attempts=3 result=escalated-pass review=clean",
            "outcome: X6 model=sonnet attempts=2 result=blocked review=none",
            "outcome: X9 model=haiku attempts=1 result=pass review=clean",
        ])
        outcomes, parse_notes = rs.parse_outcomes(notes_text)
        card = rs.build_scorecard("demo-like", tasks, outcomes, parse_notes,
                                  cost=None, expensive_tiers=EXP)

        # Top-level key set — schema lock.
        self.assertEqual(frozenset(card), {
            "schema_version", "kit", "generated_at", "tasks", "quality",
            "model_mix", "review", "cost", "notes",
        })

        q = card["quality"]
        self.assertEqual(q["total"], 6)
        self.assertEqual(q["with_outcome"], 6)
        self.assertEqual(q["first_try_pass"], 3)
        self.assertEqual(q["retry_pass"], 1)
        self.assertEqual(q["escalated_pass"], 1)
        self.assertEqual(q["blocked"], 1)
        self.assertAlmostEqual(q["first_try_rate"], 3 / 6, places=9)
        self.assertAlmostEqual(q["escalation_rate"], 1 / 6, places=9)

        self.assertEqual(card["model_mix"], {"haiku": 1, "sonnet": 4, "fable": 1})

        rv = card["review"]
        self.assertEqual(rv["cheap_reviewed"], 4)
        self.assertEqual(rv["cheap_clean"], 3)
        self.assertAlmostEqual(rv["survival_rate"], 0.75, places=9)

        # The unknown-id outcome (X9) must not become a 7th task row.
        self.assertEqual(len(card["tasks"]), 6)
        self.assertTrue(any(
            "unknown task id" in n and "X9" in n for n in card["notes"]
        ))

    def test_zero_outcome_kit_degrades_with_none_rates_and_note(self):
        tasks = [_task("Y1", model="sonnet"), _task("Y2", model="haiku", status="pending")]
        card = rs.build_scorecard("empty-kit", tasks, {}, [], cost=None, expensive_tiers=EXP)
        q = card["quality"]
        self.assertEqual(q["total"], 2)
        self.assertEqual(q["with_outcome"], 0)
        self.assertIsNone(q["first_try_rate"])
        self.assertIsNone(q["escalation_rate"])
        self.assertIsNone(card["review"]["survival_rate"])
        self.assertEqual(card["review"]["cheap_reviewed"], 0)
        self.assertTrue(any("no outcome ledger found" in n for n in card["notes"]))

    def test_model_mix_falls_back_to_task_model_then_unspecified(self):
        tasks = [
            _task("Z1", model="opus"),   # no outcome -> falls back to the task's model field
            _task("Z2", model=None),     # no outcome, no model field -> "unspecified"
            _task("Z3", model="haiku"),  # has an outcome -> effective model from the outcome
        ]
        notes_text = "outcome: Z3 model=haiku attempts=1 result=pass review=clean"
        outcomes, _ = rs.parse_outcomes(notes_text)
        card = rs.build_scorecard("mix-kit", tasks, outcomes, [], cost=None,
                                  expensive_tiers=EXP)
        self.assertEqual(card["model_mix"], {"opus": 1, "unspecified": 1, "haiku": 1})


# ---- 3b. budget-stop (T9, graph-convergence) -----------------------------------------------------
#
# `result=budget-stop` is a FIFTH value in the outcome grammar (RESULTS), added by the
# graph-convergence kit's T9 task: the drivers' optional PLAN.md `budget:` dial writes it when
# a declared dispatch/escalation/consult cap stops a run cleanly, before any dispatch. It must
# parse like any other result, appear in the per-task rows (never hidden), and be counted
# SEPARATELY from — never folded into — the first-try/escalation-rate quality signals, since a
# budget stop carries no verdict about whether the tier could have done the work.


class BudgetStopResultTests(unittest.TestCase):
    def test_parse_outcomes_accepts_budget_stop_with_run_id(self):
        text = ("outcome: A1 model=sonnet attempts=0 result=budget-stop review=none "
                "run=2026-07-26-9f3a")
        outcomes, notes = rs.parse_outcomes(text)
        self.assertEqual(notes, [])
        self.assertEqual(outcomes, {
            "A1": {"model": "sonnet", "attempts": 0, "result": "budget-stop",
                   "review": "none", "run": "2026-07-26-9f3a"},
        })

    def test_build_scorecard_excludes_budget_stop_from_rates_counts_it_separately(self):
        tasks = [
            _task("P1", model="haiku"),
            _task("P2", model="sonnet"),
            _task("P3", model="sonnet", status="pending"),
        ]
        notes_text = "\n".join([
            "outcome: P1 model=haiku attempts=1 result=pass review=clean",
            "outcome: P2 model=sonnet attempts=2 result=retry-pass review=clean",
            "outcome: P3 model=sonnet attempts=0 result=budget-stop review=none "
            "run=2026-07-26-aaaa",
        ])
        outcomes, parse_notes = rs.parse_outcomes(notes_text)
        card = rs.build_scorecard("budget-kit", tasks, outcomes, parse_notes,
                                  cost=None, expensive_tiers=EXP)
        q = card["quality"]
        # Only P1/P2 count toward with_outcome and the rates -- P3's budget-stop is excluded
        # from both, not folded into "blocked" or any other bucket.
        self.assertEqual(q["with_outcome"], 2)
        self.assertEqual(q["first_try_pass"], 1)
        self.assertEqual(q["retry_pass"], 1)
        self.assertEqual(q["escalated_pass"], 0)
        self.assertEqual(q["blocked"], 0)
        self.assertEqual(q["budget_stop"], 1)
        self.assertAlmostEqual(q["first_try_rate"], 1 / 2, places=9)
        self.assertAlmostEqual(q["escalation_rate"], 0 / 2, places=9)

        # The budget-stopped task still gets its own row -- never hidden.
        p3_row = next(r for r in card["tasks"] if r["id"] == "P3")
        self.assertEqual(p3_row["result"], "budget-stop")
        self.assertEqual(p3_row["attempts"], 0)
        self.assertEqual(p3_row["run"], "2026-07-26-aaaa")

        self.assertTrue(any("budget-stop" in n and "excluded" in n for n in card["notes"]))

    def test_all_budget_stop_kit_has_with_outcome_zero_but_no_false_no_ledger_note(self):
        tasks = [_task("Q1", model="sonnet", status="pending")]
        notes_text = "outcome: Q1 model=sonnet attempts=0 result=budget-stop review=none"
        outcomes, parse_notes = rs.parse_outcomes(notes_text)
        card = rs.build_scorecard("all-budget-stop", tasks, outcomes, parse_notes,
                                  cost=None, expensive_tiers=EXP)
        q = card["quality"]
        self.assertEqual(q["with_outcome"], 0)
        self.assertEqual(q["budget_stop"], 1)
        self.assertIsNone(q["first_try_rate"])
        self.assertIsNone(q["escalation_rate"])
        # A kit whose only outcome is a budget-stop DOES have ledger evidence -- the "no
        # outcome ledger found" note (reserved for a truly empty ledger) must NOT fire here.
        self.assertFalse(any("no outcome ledger found" in n for n in card["notes"]))
        self.assertTrue(any("budget-stop" in n for n in card["notes"]))

    def test_live_tier_stats_excludes_budget_stop_from_completed(self):
        tasks = [
            {"id": "L1", "model": "haiku", "status": "done"},
            {"id": "L2", "model": "haiku", "status": "pending"},
        ]
        notes_text = "\n".join([
            "outcome: L1 model=haiku attempts=1 result=pass review=clean",
            "outcome: L2 model=haiku attempts=0 result=budget-stop review=none",
        ])
        outcomes, _ = rs.parse_outcomes(notes_text)
        stats, notes = rs.live_tier_stats(tasks, outcomes, [])
        self.assertEqual(stats["haiku"]["completed"], 1)
        self.assertEqual(stats["haiku"]["first_try"], 1)
        self.assertAlmostEqual(stats["haiku"]["rate"], 1.0, places=9)
        self.assertTrue(any("budget-stop" in n and "L2" in n for n in notes))

    def test_history_tier_stats_excludes_budget_stop_from_with_outcome(self):
        tasks = [
            {"id": "H1", "model": "sonnet", "status": "done"},
            {"id": "H2", "model": "sonnet", "status": "pending"},
        ]
        notes_text = "\n".join([
            "outcome: H1 model=sonnet attempts=1 result=pass review=clean",
            "outcome: H2 model=sonnet attempts=0 result=budget-stop review=none",
        ])
        outcomes, _ = rs.parse_outcomes(notes_text)
        stats, notes = rs.history_tier_stats(tasks, outcomes, [])
        self.assertEqual(stats["sonnet"]["with_outcome"], 1)
        self.assertEqual(stats["sonnet"]["first_try"], 1)
        self.assertAlmostEqual(stats["sonnet"]["first_try_rate"], 1.0, places=9)
        self.assertTrue(any("budget-stop" in n and "H2" in n for n in notes))


# ---- 3c. budget_stop is an OPTIONAL quality key (PLAN D6 optionality) ------------------------
#
# `budget_stop` shipped UNCONDITIONALLY in the quality block, which changed the `--json` output
# of all 27 already-executed kits -- none of which can carry a budget-stop, because the result
# value did not exist when they ran. Every other field this kit added is conditional (`run`/
# `parent`/`failure` on a task row, `lineage`/`failure_breakdown` on the history card); this one
# now matches them. Absent means "no budget stop to report"; a zero is never emitted.


class BudgetStopKeyOptionalityTests(unittest.TestCase):
    def test_field_less_legacy_kit_quality_has_no_budget_stop_key(self):
        tasks = [_task("Z1", model="haiku"), _task("Z2", model="sonnet")]
        notes_text = "\n".join([
            "outcome: Z1 model=haiku attempts=1 result=pass review=clean",
            "outcome: Z2 model=sonnet attempts=2 result=retry-pass review=revised",
        ])
        outcomes, parse_notes = rs.parse_outcomes(notes_text)
        card = rs.build_scorecard("legacy-kit", tasks, outcomes, parse_notes,
                                  cost=None, expensive_tiers=EXP)
        self.assertNotIn("budget_stop", card["quality"])
        # The pre-kit key set, in the pre-kit order -- the thing the goldens protect.
        self.assertEqual(list(card["quality"]), [
            "total", "with_outcome", "first_try_pass", "retry_pass", "escalated_pass",
            "blocked", "first_try_rate", "escalation_rate",
        ])

    def test_kit_with_a_budget_stop_does_carry_the_key(self):
        tasks = [_task("Z1", model="haiku"), _task("Z2", model="sonnet", status="pending")]
        notes_text = "\n".join([
            "outcome: Z1 model=haiku attempts=1 result=pass review=clean",
            "outcome: Z2 model=sonnet attempts=0 result=budget-stop review=none",
        ])
        outcomes, parse_notes = rs.parse_outcomes(notes_text)
        card = rs.build_scorecard("stopped-kit", tasks, outcomes, parse_notes,
                                  cost=None, expensive_tiers=EXP)
        self.assertEqual(card["quality"]["budget_stop"], 1)
        # Present, and in its documented slot: right after `blocked`, before the rates.
        self.assertEqual(list(card["quality"]), [
            "total", "with_outcome", "first_try_pass", "retry_pass", "escalated_pass",
            "blocked", "budget_stop", "first_try_rate", "escalation_rate",
        ])


# ---- 3d. a budget-stop never supersedes a recorded verdict ----------------------------------
#
# `parse_outcomes` is last-wins, and `budget-stop` is the only result value that is NOT a
# verdict. Resuming an already-`blocked` task after the cap is spent is an ordinary gesture and
# the drivers' budget gate fires before any status check, so a budget-stop line for a task id
# that already carries a verdict is reachable without any unusual flag. Left as plain last-wins
# it ERASES the verdict and its `failure=` class from the kit card and from `--history`.


class BudgetStopNeverSupersedesVerdictTests(unittest.TestCase):
    BLOCKED = ("outcome: W1 model=sonnet attempts=2 result=blocked review=revised "
               "run=2026-07-26-1111 failure=verification")
    STOP = ("outcome: W1 model=sonnet attempts=0 result=budget-stop review=none "
            "run=2026-07-26-2222")

    def test_verdict_then_budget_stop_keeps_the_verdict(self):
        outcomes, notes = rs.parse_outcomes(self.BLOCKED + "\n" + self.STOP)
        self.assertEqual(outcomes["W1"]["result"], "blocked")
        self.assertEqual(outcomes["W1"]["failure"], "verification")
        self.assertEqual(outcomes["W1"]["run"], "2026-07-26-1111")
        self.assertTrue(any("budget-stop" in n and "verdict is kept" in n for n in notes))

    def test_verdict_survives_into_the_kit_card_and_the_failure_breakdown(self):
        tasks = [_task("W1", model="sonnet", status="blocked")]
        outcomes, parse_notes = rs.parse_outcomes(self.BLOCKED + "\n" + self.STOP)
        card = rs.build_scorecard("resumed-kit", tasks, outcomes, parse_notes,
                                  cost=None, expensive_tiers=EXP)
        q = card["quality"]
        self.assertEqual(q["with_outcome"], 1)
        self.assertEqual(q["blocked"], 1)
        self.assertNotIn("budget_stop", q)
        row = card["tasks"][0]
        self.assertEqual(row["result"], "blocked")
        self.assertEqual(row["failure"], "verification")
        # The `failure=` class still reaches D9's per-tier breakdown.
        breakdown, _ = rs.build_failure_breakdown(
            [{"kit": "resumed-kit", "tasks": tasks, "outcomes": outcomes, "events": []}])
        self.assertEqual(breakdown["sonnet"]["verification"], 1)

    def test_budget_stop_then_verdict_takes_the_verdict(self):
        # Reverse order is ordinary last-wins: the task WAS eventually dispatched, and that
        # dispatch is the evidence. No note, nothing special.
        outcomes, notes = rs.parse_outcomes(self.STOP + "\n" + self.BLOCKED)
        self.assertEqual(outcomes["W1"]["result"], "blocked")
        self.assertEqual(outcomes["W1"]["failure"], "verification")
        self.assertEqual(notes, [])

    def test_budget_stop_alone_still_records_normally(self):
        outcomes, notes = rs.parse_outcomes(self.STOP)
        self.assertEqual(outcomes["W1"]["result"], "budget-stop")
        self.assertEqual(outcomes["W1"]["run"], "2026-07-26-2222")
        self.assertEqual(notes, [])

    def test_budget_stop_after_a_budget_stop_is_plain_last_wins(self):
        second = self.STOP.replace("2026-07-26-2222", "2026-07-26-3333")
        outcomes, notes = rs.parse_outcomes(self.STOP + "\n" + second)
        self.assertEqual(outcomes["W1"]["result"], "budget-stop")
        self.assertEqual(outcomes["W1"]["run"], "2026-07-26-3333")
        self.assertEqual(notes, [])


# ---- 4. session_cost_summary ---------------------------------------------------------------------


class SessionCostSummaryTests(unittest.TestCase):
    def test_hand_math_actual_usd_and_frontier_counterfactual(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            proj = root / "projects" / "slug"
            proj.mkdir(parents=True)
            (proj / "SESS.jsonl").write_text(
                _line("fake-haiku-1", "m1", inp=1000, out=200,
                      cache_read=500, cache_write=100) + "\n"
            )
            cost, notes = rs.session_cost_summary(
                "SESS", str(root / "projects"), [], [], True, None, P)

            self.assertEqual(notes, [])
            expected_actual = (
                1000 * 1.0 + 200 * 5.0 + 500 * 1.0 * 0.1 + 100 * 1.0 * 1.25
            ) / 1e6
            self.assertAlmostEqual(cost["actual_usd"], expected_actual, places=9)

            self.assertEqual(cost["counterfactual_model"]["key"], "fake-frontier-1")
            expected_cf = (
                1000 * 15.0 + 200 * 75.0 + 500 * 15.0 * 0.1 + 100 * 15.0 * 1.25
            ) / 1e6
            self.assertAlmostEqual(cost["counterfactual_usd"], expected_cf, places=9)
            self.assertAlmostEqual(
                cost["delta_usd"], expected_cf - expected_actual, delta=1e-9
            )
            self.assertEqual(cost["files_scanned"], 1)
            self.assertEqual(cost["pricing_cached"], "2020-01-01")

    def test_dedupe_across_main_transcript_and_subagent_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            proj = root / "projects" / "slug"
            proj.mkdir(parents=True)
            (proj / "SESS.jsonl").write_text(
                _line("fake-haiku-1", "shared-1", inp=1000, out=200) + "\n"
            )
            tasks_dir = root / "tasks"
            tasks_dir.mkdir()
            (tasks_dir / "sub.output").write_text("\n".join([
                _line("fake-haiku-1", "shared-1", inp=1000, out=200),  # dup id -> ignored
                _line("fake-sonnet-1", "sub-2", inp=500, out=50),
            ]) + "\n")

            cost, notes = rs.session_cost_summary(
                "SESS", str(root / "projects"), [tasks_dir], [], False, None, P)

            self.assertEqual(notes, [])
            self.assertEqual(cost["files_scanned"], 2)
            expected_actual = (
                (1000 * 1.0 + 200 * 5.0)      # the shared message, counted ONCE
                + (500 * 3.0 + 50 * 15.0)     # the subagent-only message
            ) / 1e6
            self.assertAlmostEqual(cost["actual_usd"], expected_actual, places=9)

    def test_missing_session_returns_none_and_note(self):
        with tempfile.TemporaryDirectory() as td:
            projects_dir = Path(td) / "projects"
            projects_dir.mkdir()
            cost, notes = rs.session_cost_summary(
                "NO-SUCH-SESSION", str(projects_dir), [], [], True, None, P)
            self.assertIsNone(cost)
            self.assertEqual(len(notes), 1)
            self.assertIn("NO-SUCH-SESSION", notes[0])

    def test_bad_vs_raises_valueerror(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            proj = root / "projects" / "slug"
            proj.mkdir(parents=True)
            (proj / "SESS.jsonl").write_text(
                _line("fake-haiku-1", "m1", inp=1, out=1) + "\n"
            )
            with self.assertRaises(ValueError):
                rs.session_cost_summary(
                    "SESS", str(root / "projects"), [], [], True,
                    "not-a-real-model-in-P", P)


# ---- 5. CLI end-to-end ----------------------------------------------------------------------


class CliEndToEndTests(unittest.TestCase):
    def test_json_end_to_end_expected_numbers(self):
        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            kits_root.mkdir()
            _write_kit(kits_root, "cli-e2e", CLI_TASKS_MD, CLI_NOTES_MD)
            result = _run_cli(["cli-e2e", "--kits-dir", str(kits_root), "--json"])

        self.assertEqual(result.returncode, 0, result.stderr)
        card = json.loads(result.stdout)
        self.assertEqual(card["schema_version"], 1)
        self.assertEqual(card["kit"], "cli-e2e")

        q = card["quality"]
        self.assertEqual(q["total"], 3)
        self.assertEqual(q["with_outcome"], 3)
        self.assertEqual(q["first_try_pass"], 1)
        self.assertEqual(q["retry_pass"], 1)
        self.assertEqual(q["escalated_pass"], 0)
        self.assertEqual(q["blocked"], 1)
        self.assertAlmostEqual(q["first_try_rate"], 1 / 3, places=9)
        self.assertAlmostEqual(q["escalation_rate"], 0.0, places=9)

        self.assertEqual(card["model_mix"], {"haiku": 1, "sonnet": 2})

        rv = card["review"]
        self.assertEqual(rv["cheap_reviewed"], 2)
        self.assertEqual(rv["cheap_clean"], 1)
        self.assertAlmostEqual(rv["survival_rate"], 0.5, places=9)

        self.assertIsNone(card["cost"])
        self.assertTrue(any("no session provided" in n for n in card["notes"]))

    def test_markdown_mode_has_five_h2s_in_order(self):
        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            kits_root.mkdir()
            _write_kit(kits_root, "cli-e2e-md", CLI_TASKS_MD, CLI_NOTES_MD)
            result = _run_cli(["cli-e2e-md", "--kits-dir", str(kits_root)])

        self.assertEqual(result.returncode, 0, result.stderr)
        positions = [result.stdout.index(h2) for h2 in EXPECTED_H2S]
        self.assertEqual(positions, sorted(positions))
        self.assertTrue(result.stdout.startswith("# Routing scorecard — cli-e2e-md"))

    def test_session_transcript_not_found_reports_distinctly(self):
        # --session passed but no matching transcript: the verdict/Dollars must say
        # "transcript not found", never the misleading "(no --session)".
        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            kits_root.mkdir()
            _write_kit(kits_root, "cli-nosess", CLI_TASKS_MD, CLI_NOTES_MD)
            empty_projects = Path(td) / "projects"
            empty_projects.mkdir()
            result = _run_cli(["cli-nosess", "--kits-dir", str(kits_root),
                               "--session", "no-such-session-xyz",
                               "--projects-dir", str(empty_projects), "--no-subagents"])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("transcript not found", result.stdout)
        self.assertNotIn("(no --session)", result.stdout)
        self.assertIn("no transcript found for the given --session", result.stdout)

    def test_kit_without_notes_md_exits_zero_with_degradation_note(self):
        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            kits_root.mkdir()
            _write_kit(kits_root, "no-notes", CLI_TASKS_MD, notes_md=None)
            result = _run_cli(["no-notes", "--kits-dir", str(kits_root), "--json"])

        self.assertEqual(result.returncode, 0, result.stderr)
        card = json.loads(result.stdout)
        self.assertTrue(any("no NOTES.md" in n for n in card["notes"]))

    def test_malformed_tasks_md_exits_nonzero_and_names_the_file(self):
        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            kits_root.mkdir()
            _write_kit(kits_root, "bad-kit", BAD_STATUS_TASKS_MD)
            result = _run_cli(["bad-kit", "--kits-dir", str(kits_root), "--json"])

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("TASKS.md", result.stderr)

    def test_no_args_exits_nonzero(self):
        result = _run_cli([])
        self.assertNotEqual(result.returncode, 0)

    def test_demo_with_kit_arg_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            kits_root.mkdir()
            result = _run_cli(["some-slug", "--kits-dir", str(kits_root), "--demo"])
        self.assertNotEqual(result.returncode, 0)

    def test_demo_markdown_exits_zero(self):
        result = _run_cli(["--demo"])
        self.assertEqual(result.returncode, 0, result.stderr)
        for h2 in EXPECTED_H2S:
            self.assertIn(h2, result.stdout)

    def test_demo_json_exits_zero_and_matches_pinned_quality_totals(self):
        result = _run_cli(["--demo", "--json"])
        self.assertEqual(result.returncode, 0, result.stderr)
        card = json.loads(result.stdout)
        self.assertEqual(card["schema_version"], 1)
        q = card["quality"]
        self.assertEqual(q["total"], 6)
        self.assertEqual(q["with_outcome"], 6)
        self.assertEqual(q["first_try_pass"], 3)
        self.assertEqual(q["retry_pass"], 1)
        self.assertEqual(q["escalated_pass"], 1)
        self.assertEqual(q["blocked"], 1)


# ---- 6. READ-ONLY byte-snapshot proof --------------------------------------------------------


class ReadOnlyProofTests(unittest.TestCase):
    def test_full_cli_run_leaves_kit_and_projects_tree_byte_identical(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            kits_root = root / "kits"
            kits_root.mkdir()
            _write_kit(kits_root, "readonly-kit", CLI_TASKS_MD, CLI_NOTES_MD)

            projects_root = root / "projects"
            proj = projects_root / "slug"
            proj.mkdir(parents=True)
            (proj / "READONLY.jsonl").write_text(
                _line("totally-fake-model-for-readonly-proof", "ro-1", inp=10, out=10) + "\n"
            )

            def snapshot():
                files = sorted(p for p in root.rglob("*") if p.is_file())
                return [str(p) for p in files], {str(p): p.read_bytes() for p in files}

            before_paths, before_bytes = snapshot()
            result = _run_cli([
                "readonly-kit", "--kits-dir", str(kits_root),
                "--session", "READONLY", "--projects-dir", str(projects_root),
                "--no-subagents", "--json",
            ])
            after_paths, after_bytes = snapshot()

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(before_paths, after_paths)
            self.assertEqual(before_bytes, after_bytes)


# ---- 7. T2 byte-stability goldens (graph-convergence) ----------------------------------------
#
# Captured verbatim from the UNMODIFIED engine (before run=/parent=/failure= parsing landed)
# via ``python3 bin/routing_scorecard.py --demo`` / ``--demo --history``, per PLAN D6's
# tripwire: a field-less kit's rendered output must stay byte-identical after T2. Neither
# DEMO_TASKS_MD/DEMO_NOTES_MD nor the DEMO_HIST_* fixtures carry run=/parent=/failure=, so
# these two goldens are the proof that T2's parsing is genuinely additive.

GOLDEN_DEMO_MARKDOWN = "# Routing scorecard — fusion-demo\n\n## Verdict\n\n**3/6 tasks passed verify first-try on their pinned model · cheap-model review survival 75% · $4.59 actual vs $16.80 all-Fable 5 (Δ $12.21 saved)**\n\n## Task outcomes\n\n| Task | Model | Status | Result | Attempts | Review |\n|---|---|---|---|---:|---|\n| D1 | haiku | done | pass | 1 | clean |\n| D2 | sonnet | done | pass | 1 | clean |\n| D3 | sonnet | done | pass | 1 | revised |\n| D4 | sonnet | done | retry-pass | 2 | clean |\n| D5 | fable | done | escalated-pass | 3 | clean |\n| D6 | sonnet | blocked | blocked | 2 | none |\n\n## Model mix\n\n| Model | Tasks |\n|---|---:|\n| haiku | 1 |\n| sonnet | 4 |\n| fable | 1 |\n\n## Review survival\n\n- Cheap-model tasks reviewed: 4\n- Reviewed clean (survived unchanged): 3\n- Survival rate: 75%\n\n*Cheap = a task whose effective model is not in the expensive tiers (frontier/opus); survival = the review-clean share of reviewed cheap tasks — the share of cheap-model output that passed independent review unchanged.*\n\n## Dollars\n\n- Actual (mixed workflow): $4.59\n- All-Fable 5: $16.80\n- Δ saved vs all-Fable 5: $12.21\n- Ratio: 3.66×\n- Files scanned: 1\n- Prices cached 2026-07-24\n\nNotes:\n- unrecognized outcome line: 'outcome: D9 result=???'\n"

GOLDEN_DEMO_HISTORY_MARKDOWN = '# Routing history — cross-kit per-tier track record\n\n## Verdict\n\n**3 kits · 5/9 first-try · $4.59 actual vs $16.80 all-Fable 5 over 1/3 kits (partial)**\n\n## Per-tier track record\n\n| Tier | Pinned | With outcome | First-try | Retry | Escalated | Blocked | First-try rate | Escalation rate |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|\n| haiku | 3 | 3 | 2 | 1 | 0 | 0 | 67% | 0% |\n| sonnet | 6 | 5 | 2 | 1 | 1 | 1 | 40% | 20% |\n| opus | 2 | 1 | 1 | 0 | 0 | 0 | 100% | 0% |\n| frontier | 1 | 0 | 0 | 0 | 0 | 0 | n/a | n/a |\n\n## Role quality\n\nImplementer quality: see the per-tier track record above (outcome ledger).\n\n| Role | Events | With precision | Findings | Confirmed | Precision | Accepted | Revised | Blocked | Unrecorded |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n| verifier | 2 | 2 | 5 | 3 | 60% | 1 | 1 | 0 | 0 |\n| reviewer | 1 | 1 | 2 | 1 | 50% | 1 | 0 | 0 | 0 |\n| escalation | 1 | n/a | n/a | n/a | n/a | 1 | 0 | 0 | 0 |\n\n- verifier haiku: 1 event(s), 1 with recorded precision, findings 2, confirmed 2, precision 100%\n- verifier sonnet: 1 event(s), 1 with recorded precision, findings 3, confirmed 1, precision 33%\n- reviewer opus: 1 event(s), 1 with recorded precision, findings 2, confirmed 1, precision 50%\n- Architect: 2 brief defects across 1 kits (floor — kits run before role-ledger adoption record none)\n  - kinds: stale-pin 1, tautological-verify 1\n\n## Re-route history\n\n- Events: 1 (0 applied, 1 advisory)\n- haiku: applied_from 0, applied_to 0, advisory_from 1, advisory_to 0\n- sonnet: applied_from 0, applied_to 0, advisory_from 0, advisory_to 1\n\n## Kits\n\n| Kit | Tasks | With outcome | First-try | Sessions | Actual $ |\n|---|---:|---:|---:|---:|---:|\n| hist-alpha | 5 | 5 | 3 | 1 | $4.59 |\n| hist-beta | 4 | 4 | 2 | 0 | n/a |\n| hist-gamma | 3 | 0 | 0 | 0 | n/a |\n\n## Dollars\n\n- Actual (mixed workflow): $4.59\n- All-Fable 5: $16.80\n- Δ saved vs all-Fable 5: $12.21\n- Ratio: 3.66×\n- Sessions priced: 1/1\n- Coverage: over 1/3 kits (partial)\n- Prices cached 2026-07-24\n\nNotes:\n- hist-gamma: no outcome ledger — status-only\n- not-a-kit: no TASKS.md — skipped\n'


# The `--json` surface, added to the tripwire after T9's `budget_stop` key shipped
# UNCONDITIONALLY and changed the quality block of all 27 already-executed kits without any
# golden noticing. The two markdown goldens above cover only the rendered surface, and
# `render_markdown` never printed `budget_stop` -- so a JSON-only regression was invisible to
# them by construction. These two goldens were captured the same way as the markdown pair:
# from the PRE-KIT engine at git HEAD (`git show HEAD:bin/routing_scorecard.py`), run as
# `--demo --json` / `--demo --history --json`.
#
# Two keys are dropped before comparison, and ONLY these two, because both are non-deterministic
# by design rather than part of the contract: `generated_at` (a wall-clock timestamp) and, on
# the history card, `kits_dir` (the per-run temp directory `--demo` synthesizes). Everything
# else -- every key, every value, and their ORDER (the comparison re-serializes the parsed card,
# so a reordered or added key fails) -- is pinned. A failure here means a change is NOT additive;
# fix the change, never the golden.

GOLDEN_DEMO_JSON = '{"schema_version": 1, "kit": "fusion-demo", "tasks": [{"id": "D1", "title": "cheap first-try task", "status": "done", "model": "haiku", "effective_model": "haiku", "result": "pass", "attempts": 1, "review": "clean"}, {"id": "D2", "title": "sonnet clean task", "status": "done", "model": "sonnet", "effective_model": "sonnet", "result": "pass", "attempts": 1, "review": "clean"}, {"id": "D3", "title": "sonnet revised task", "status": "done", "model": "sonnet", "effective_model": "sonnet", "result": "pass", "attempts": 1, "review": "revised"}, {"id": "D4", "title": "sonnet retry task", "status": "done", "model": "sonnet", "effective_model": "sonnet", "result": "retry-pass", "attempts": 2, "review": "clean"}, {"id": "D5", "title": "escalated frontier task", "status": "done", "model": "fable", "effective_model": "fable", "result": "escalated-pass", "attempts": 3, "review": "clean"}, {"id": "D6", "title": "blocked task", "status": "blocked", "model": "sonnet", "effective_model": "sonnet", "result": "blocked", "attempts": 2, "review": "none"}], "quality": {"total": 6, "with_outcome": 6, "first_try_pass": 3, "retry_pass": 1, "escalated_pass": 1, "blocked": 1, "first_try_rate": 0.5, "escalation_rate": 0.16666666666666666}, "model_mix": {"haiku": 1, "sonnet": 4, "fable": 1}, "review": {"cheap_reviewed": 4, "cheap_clean": 3, "survival_rate": 0.75}, "cost": {"session": "fusion-demo", "files_scanned": 1, "actual_usd": 4.59, "counterfactual_usd": 16.8, "counterfactual_model": {"key": "claude-fable-5", "display": "Fable 5"}, "delta_usd": 12.21, "ratio": 3.6601307189542487, "pricing_cached": "2026-07-24"}, "notes": ["unrecognized outcome line: \'outcome: D9 result=???\'"]}'

GOLDEN_DEMO_HISTORY_JSON = '{"schema_version": 2, "kits": [{"kit": "hist-alpha", "tasks": 5, "with_outcome": 5, "first_try_pass": 3, "retry_pass": 1, "escalated_pass": 1, "blocked": 0, "sessions": ["hist-alpha-session"], "cost": {"actual_usd": 4.59, "counterfactual_usd": 16.8, "delta_usd": 12.21, "ratio": 3.6601307189542487, "sessions_priced": 1, "files_scanned": 1}}, {"kit": "hist-beta", "tasks": 4, "with_outcome": 4, "first_try_pass": 2, "retry_pass": 1, "escalated_pass": 0, "blocked": 1, "sessions": [], "cost": null}, {"kit": "hist-gamma", "tasks": 3, "with_outcome": 0, "first_try_pass": 0, "retry_pass": 0, "escalated_pass": 0, "blocked": 0, "sessions": [], "cost": null}], "tiers": {"haiku": {"pinned": 3, "with_outcome": 3, "first_try": 2, "retry_pass": 1, "escalated_pass": 0, "blocked": 0, "first_try_rate": 0.6666666666666666, "escalation_rate": 0.0, "reroutes": {"applied_from": 0, "applied_to": 0, "advisory_from": 1, "advisory_to": 0}}, "sonnet": {"pinned": 6, "with_outcome": 5, "first_try": 2, "retry_pass": 1, "escalated_pass": 1, "blocked": 1, "first_try_rate": 0.4, "escalation_rate": 0.2, "reroutes": {"applied_from": 0, "applied_to": 0, "advisory_from": 0, "advisory_to": 1}}, "opus": {"pinned": 2, "with_outcome": 1, "first_try": 1, "retry_pass": 0, "escalated_pass": 0, "blocked": 0, "first_try_rate": 1.0, "escalation_rate": 0.0, "reroutes": {"applied_from": 0, "applied_to": 0, "advisory_from": 0, "advisory_to": 0}}, "frontier": {"pinned": 1, "with_outcome": 0, "first_try": 0, "retry_pass": 0, "escalated_pass": 0, "blocked": 0, "first_try_rate": null, "escalation_rate": null, "reroutes": {"applied_from": 0, "applied_to": 0, "advisory_from": 0, "advisory_to": 0}}}, "reroutes": {"events": 1, "applied": 0, "advisory": 1}, "roles": {"verifier": {"events": 2, "with_precision": 2, "findings": 5, "confirmed": 3, "precision": 0.6, "results": {"accepted": 1, "revised": 1, "blocked": 0, "unrecorded": 0}, "by_tier": {"haiku": {"events": 1, "with_precision": 1, "findings": 2, "confirmed": 2, "precision": 1.0}, "sonnet": {"events": 1, "with_precision": 1, "findings": 3, "confirmed": 1, "precision": 0.3333333333333333}, "opus": {"events": 0, "with_precision": 0, "findings": 0, "confirmed": 0, "precision": null}, "frontier": {"events": 0, "with_precision": 0, "findings": 0, "confirmed": 0, "precision": null}}}, "escalation": {"events": 1, "results": {"accepted": 1, "revised": 0, "blocked": 0, "unrecorded": 0}}, "reviewer": {"events": 1, "findings": 2, "confirmed": 1, "precision": 0.5, "results": {"accepted": 1, "revised": 0, "blocked": 0, "unrecorded": 0}, "by_tier": {"haiku": {"events": 0, "with_precision": 0, "findings": 0, "confirmed": 0, "precision": null}, "sonnet": {"events": 0, "with_precision": 0, "findings": 0, "confirmed": 0, "precision": null}, "opus": {"events": 1, "with_precision": 1, "findings": 2, "confirmed": 1, "precision": 0.5}, "frontier": {"events": 0, "with_precision": 0, "findings": 0, "confirmed": 0, "precision": null}}}, "architect": {"defects": 2, "kits_recording": 1, "by_kind": {"stale-pin": 1, "tautological-verify": 1}, "by_kit": {"hist-alpha": 2}}}, "dollars": {"kits_with_sessions": 1, "kits_total": 3, "sessions_found": 1, "sessions_priced": 1, "actual_usd": 4.59, "counterfactual_usd": 16.8, "delta_usd": 12.21, "ratio": 3.6601307189542487, "counterfactual_model": {"key": "claude-fable-5", "display": "Fable 5"}, "coverage": "partial", "pricing_cached": "2026-07-24"}, "notes": ["hist-gamma: no outcome ledger \\u2014 status-only", "not-a-kit: no TASKS.md \\u2014 skipped"]}'

# The volatile keys, named once so the two tests and the comment above cannot drift apart.
_JSON_GOLDEN_VOLATILE = ("generated_at", "kits_dir")


def _json_card_without_volatile_keys(stdout):
    """Re-serialize a `--json` card with only the two non-deterministic keys removed.

    Re-serializing (rather than comparing parsed dicts) keeps KEY ORDER in the comparison, so
    an inserted key fails the golden even when its value would be ignorable.
    """
    card = json.loads(stdout)
    for key in _JSON_GOLDEN_VOLATILE:
        card.pop(key, None)
    return json.dumps(card)


class T2GoldenByteStabilityTests(unittest.TestCase):
    def test_demo_markdown_byte_identical_to_pre_t2_capture(self):
        result = _run_cli(["--demo"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, GOLDEN_DEMO_MARKDOWN)

    def test_demo_history_markdown_byte_identical_to_pre_t2_capture(self):
        result = _run_cli(["--demo", "--history"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, GOLDEN_DEMO_HISTORY_MARKDOWN)

    def test_demo_json_identical_to_pre_kit_capture(self):
        result = _run_cli(["--demo", "--json"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(_json_card_without_volatile_keys(result.stdout), GOLDEN_DEMO_JSON)

    def test_demo_history_json_identical_to_pre_kit_capture(self):
        result = _run_cli(["--demo", "--history", "--json"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(_json_card_without_volatile_keys(result.stdout),
                         GOLDEN_DEMO_HISTORY_JSON)

    def test_demo_json_quality_block_carries_no_budget_stop_key(self):
        # The specific regression the two JSON goldens were added for, asserted on its own so a
        # failure names the cause instead of diffing 1.6 KB. A field-less legacy kit cannot
        # contain a budget-stop -- the result value did not exist when it ran -- so the key must
        # be ABSENT, not present-and-zero.
        result = _run_cli(["--demo", "--json"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("budget_stop", json.loads(result.stdout)["quality"])


# ---- 8. T2 parse_outcomes: run=/parent=/failure= ---------------------------------------------


class ParseOutcomesLineageTests(unittest.TestCase):
    def test_run_parent_failure_all_parsed(self):
        text = ("outcome: T7 model=fable attempts=3 result=escalated-pass review=clean "
                "run=2026-07-26-9f3a parent=T4 failure=verification")
        outcomes, notes = rs.parse_outcomes(text)
        self.assertEqual(notes, [])
        self.assertEqual(outcomes["T7"], {
            "model": "fable", "attempts": 3, "result": "escalated-pass", "review": "clean",
            "run": "2026-07-26-9f3a", "parent": "T4", "failure": "verification",
        })

    def test_legacy_line_has_no_new_keys(self):
        text = "outcome: A1 model=haiku attempts=1 result=pass review=clean"
        outcomes, notes = rs.parse_outcomes(text)
        self.assertEqual(notes, [])
        self.assertEqual(set(outcomes["A1"]), {"model", "attempts", "result", "review"})

    def test_self_parent_dropped_with_note(self):
        text = "outcome: T4 model=sonnet attempts=1 result=blocked review=none parent=T4"
        outcomes, notes = rs.parse_outcomes(text)
        self.assertNotIn("parent", outcomes["T4"])
        self.assertTrue(any("own task id" in n for n in notes))

    def test_unknown_failure_class_dropped_with_note(self):
        text = ("outcome: T4 model=sonnet attempts=2 result=blocked review=none "
                "failure=laziness")
        outcomes, notes = rs.parse_outcomes(text)
        self.assertNotIn("failure", outcomes["T4"])
        self.assertTrue(any("unknown failure class" in n for n in notes))

    def test_run_alone_is_independent_of_parent_and_failure(self):
        text = "outcome: T2 model=haiku attempts=1 result=pass review=clean run=2026-07-26-abcd"
        outcomes, notes = rs.parse_outcomes(text)
        self.assertEqual(notes, [])
        self.assertEqual(outcomes["T2"]["run"], "2026-07-26-abcd")
        self.assertNotIn("parent", outcomes["T2"])
        self.assertNotIn("failure", outcomes["T2"])


# ---- 9. T2 build_scorecard / render_markdown: row-level run/parent/failure -------------------


class BuildScorecardLineageRowTests(unittest.TestCase):
    def test_row_carries_run_parent_failure_only_when_present(self):
        tasks = [_task("T4", model="sonnet"), _task("T7", model="fable")]
        notes_text = "\n".join([
            "outcome: T4 model=sonnet attempts=1 result=pass review=clean",
            "outcome: T7 model=fable attempts=3 result=escalated-pass review=clean "
            "run=2026-07-26-9f3a parent=T4 failure=verification",
        ])
        outcomes, parse_notes = rs.parse_outcomes(notes_text)
        card = rs.build_scorecard("lineage-kit", tasks, outcomes, parse_notes,
                                  cost=None, expensive_tiers=EXP)
        rows = {r["id"]: r for r in card["tasks"]}
        self.assertEqual(set(rows["T4"]), {
            "id", "title", "status", "model", "effective_model", "result", "attempts",
            "review",
        })
        self.assertEqual(rows["T7"]["run"], "2026-07-26-9f3a")
        self.assertEqual(rows["T7"]["parent"], "T4")
        self.assertEqual(rows["T7"]["failure"], "verification")


class RenderMarkdownRunColumnTests(unittest.TestCase):
    def test_run_column_appears_only_when_a_row_carries_run(self):
        tasks = [_task("A1", model="haiku")]
        outcomes, _ = rs.parse_outcomes(
            "outcome: A1 model=haiku attempts=1 result=pass review=clean")
        card_no_run = rs.build_scorecard("k1", tasks, outcomes, [], cost=None,
                                         expensive_tiers=EXP)
        md_no_run = rs.render_markdown(card_no_run)
        self.assertNotIn("Run |", md_no_run)

        outcomes2, _ = rs.parse_outcomes(
            "outcome: A1 model=haiku attempts=1 result=pass review=clean "
            "run=2026-07-26-1234")
        card_run = rs.build_scorecard("k2", tasks, outcomes2, [], cost=None,
                                      expensive_tiers=EXP)
        md_run = rs.render_markdown(card_run)
        self.assertIn(
            "| Task | Model | Status | Result | Attempts | Review | Run |", md_run)
        self.assertIn("2026-07-26-1234", md_run)


# ---- 10. T2 build_lineage / build_failure_breakdown (pure functions) -------------------------


def _rec(kit, tasks, outcomes, events=()):
    """A scan_kits-shaped record, for build_lineage/build_failure_breakdown unit tests."""
    return {"kit": kit, "tasks": tasks, "outcomes": outcomes, "events": list(events),
            "sessions": [], "agents": [], "reviewers": [], "defects": [], "notes": []}


class BuildLineageTests(unittest.TestCase):
    def test_groups_children_under_parent_and_counts_cheap_pins(self):
        tasks = [_task("T4", model="sonnet"), _task("T7", model="fable")]
        outcomes = {
            "T4": {"model": "sonnet", "attempts": 2, "result": "blocked", "review": "none",
                   "failure": "verification"},
            "T7": {"model": "fable", "attempts": 3, "result": "escalated-pass",
                   "review": "clean", "run": "2026-07-26-9f3a", "parent": "T4",
                   "failure": "verification"},
        }
        records = [_rec("k1", tasks, outcomes)]
        groups, cheap, notes = rs.build_lineage(records, EXP)
        self.assertEqual(notes, [])
        self.assertEqual(len(groups), 1)
        g = groups[0]
        self.assertEqual((g["kit"], g["parent"], g["parent_model"], g["parent_tier"]),
                         ("k1", "T4", "sonnet", "sonnet"))
        self.assertEqual(len(g["children"]), 1)
        self.assertEqual(g["children"][0]["task"], "T7")
        self.assertEqual(g["children"][0]["run"], "2026-07-26-9f3a")
        self.assertEqual(cheap, {"haiku": 0, "sonnet": 1})

    def test_no_parent_anywhere_returns_empty(self):
        tasks = [_task("A1", model="haiku")]
        outcomes = {"A1": {"model": "haiku", "attempts": 1, "result": "pass",
                           "review": "clean"}}
        records = [_rec("k1", tasks, outcomes)]
        groups, cheap, notes = rs.build_lineage(records, EXP)
        self.assertEqual((groups, cheap, notes), ([], {}, []))

    def test_unknown_parent_is_noted_and_dropped(self):
        tasks = [_task("T7", model="fable")]
        outcomes = {
            "T7": {"model": "fable", "attempts": 1, "result": "escalated-pass",
                   "review": "clean", "parent": "GHOST"},
        }
        records = [_rec("k1", tasks, outcomes)]
        groups, cheap, notes = rs.build_lineage(records, EXP)
        self.assertEqual(groups, [])
        self.assertTrue(any("GHOST" in n and "not a known task id" in n for n in notes))

    def test_unknown_child_task_id_rejected_same_as_failure_breakdown(self):
        # F2: build_lineage and build_failure_breakdown must agree on which outcomes are
        # "known" -- a consult id absent from TASKS.md is rejected (never counted) by both,
        # never counted by one while reported "ignored" by the other.
        tasks = [_task("T4", model="sonnet")]
        outcomes = {
            "T4": {"model": "sonnet", "attempts": 1, "result": "blocked", "review": "none",
                   "failure": "verification"},
            "GHOST-CHILD": {"model": "fable", "attempts": 1, "result": "escalated-pass",
                             "review": "clean", "parent": "T4", "failure": "verification"},
        }
        records = [_rec("k1", tasks, outcomes)]
        groups, cheap, notes = rs.build_lineage(records, EXP)
        self.assertEqual(groups, [])
        self.assertTrue(any("unknown task id" in n and "GHOST-CHILD" in n for n in notes))
        # And build_failure_breakdown drops the same outcome for the same reason -- never
        # both counted-somewhere and called "ignored" in the other.
        breakdown, fb_notes = rs.build_failure_breakdown(records)
        self.assertNotIn("frontier", breakdown)
        self.assertTrue(any("unknown task id" in n and "GHOST-CHILD" in n for n in fb_notes))

    def test_parent_on_non_escalated_result_dropped_with_note(self):
        # F4: parent= is out of grammar on anything but an escalated-pass outcome -- dropped
        # with a note, never counted into a group or the cheap-pin tally.
        tasks = [_task("T4", model="sonnet"), _task("T7", model="fable")]
        outcomes = {
            "T4": {"model": "sonnet", "attempts": 1, "result": "pass", "review": "clean"},
            "T7": {"model": "fable", "attempts": 1, "result": "pass", "review": "clean",
                   "parent": "T4"},
        }
        records = [_rec("k1", tasks, outcomes)]
        groups, cheap, notes = rs.build_lineage(records, EXP)
        self.assertEqual(groups, [])
        self.assertEqual(cheap, {})
        self.assertTrue(any("out of grammar" in n for n in notes))


class BuildFailureBreakdownTests(unittest.TestCase):
    def test_counts_by_dispatch_tier(self):
        # T4 (blocked) attributes directly to its own pin (sonnet); T7 is the SEPARATE
        # escalation consult that rescued T4 (carries parent=T4), so per the Phase 1 review's
        # F3 adjudication its own failure= is excluded entirely -- the parent's outcome is the
        # sole attribution source, and "frontier" (T7's own pin) must NOT appear at all.
        tasks = [_task("T4", model="sonnet"), _task("T7", model="fable")]
        outcomes = {
            "T4": {"model": "sonnet", "attempts": 2, "result": "blocked", "review": "none",
                   "failure": "coherence"},
            "T7": {"model": "fable", "attempts": 3, "result": "escalated-pass",
                   "review": "clean", "parent": "T4", "failure": "verification"},
        }
        records = [_rec("k1", tasks, outcomes)]
        breakdown, notes = rs.build_failure_breakdown(records)
        self.assertEqual(notes, [])
        self.assertEqual(breakdown["sonnet"], {"coherence": 1})
        self.assertNotIn("frontier", breakdown)

    def test_child_outcome_never_inverts_attribution_to_the_rescuing_tier(self):
        """Regression guard for the F3 inverted-attribution defect (Phase 1 review): a
        SEPARATE consult task pinned at the rescuing tier must never have its own failure=
        counted against that tier. Only the parent's own outcome -- the tier that actually
        FAILED verification -- may contribute, even when the consult also carries the same
        failure= class on its own line."""
        tasks = [_task("T4", model="sonnet"), _task("T7", model="fable")]
        outcomes = {
            "T4": {"model": "sonnet", "attempts": 2, "result": "blocked", "review": "none",
                   "failure": "verification"},
            "T7": {"model": "fable", "attempts": 1, "result": "escalated-pass",
                   "review": "clean", "parent": "T4", "failure": "verification"},
        }
        records = [_rec("k1", tasks, outcomes)]
        breakdown, notes = rs.build_failure_breakdown(records)
        self.assertEqual(breakdown, {"sonnet": {"verification": 1}})
        self.assertNotIn("frontier", breakdown)

    def test_failure_on_non_blocked_non_escalated_result_dropped_with_note(self):
        # F4: failure= is out of grammar on a plain `pass`/`retry-pass` outcome -- dropped
        # with a note, never counted, mirroring the unknown-failure-class precedent.
        tasks = [_task("A1", model="haiku")]
        outcomes = {"A1": {"model": "haiku", "attempts": 1, "result": "pass",
                           "review": "clean", "failure": "coherence"}}
        records = [_rec("k1", tasks, outcomes)]
        breakdown, notes = rs.build_failure_breakdown(records)
        self.assertEqual(breakdown, {})
        self.assertTrue(any("out of grammar" in n for n in notes))

    def test_no_failure_anywhere_returns_empty(self):
        tasks = [_task("A1", model="haiku")]
        outcomes = {"A1": {"model": "haiku", "attempts": 1, "result": "pass",
                           "review": "clean"}}
        records = [_rec("k1", tasks, outcomes)]
        breakdown, notes = rs.build_failure_breakdown(records)
        self.assertEqual((breakdown, notes), ({}, []))


# ---- 11. T2 CLI end-to-end: --history lineage + failure breakdown ----------------------------

LINEAGE_TASKS_MD = """# TASKS — lineage-demo (synthetic test fixture)

## Phase 1 — only phase

### T4 — struggling sonnet task
- status: blocked
- model: sonnet

### T7 — escalation consult for T4
- status: done
- model: fable
"""

LINEAGE_NOTES_MD = """# NOTES — lineage-demo (synthetic test fixture)

## Outcome ledger
outcome: T4 model=sonnet attempts=2 result=blocked review=none run=2026-07-26-1111 failure=verification
outcome: T7 model=fable attempts=3 result=escalated-pass review=clean run=2026-07-26-2222 parent=T4 failure=verification
"""


class CliLineageEndToEndTests(unittest.TestCase):
    def test_history_json_carries_lineage_and_failure_breakdown_when_present(self):
        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            kits_root.mkdir()
            _write_kit(kits_root, "lineage-demo", LINEAGE_TASKS_MD, LINEAGE_NOTES_MD)
            result = _run_cli(["--history", "--kits-dir", str(kits_root), "--json"])

        self.assertEqual(result.returncode, 0, result.stderr)
        card = json.loads(result.stdout)

        lineage = card["lineage"]
        self.assertEqual(len(lineage["groups"]), 1)
        g = lineage["groups"][0]
        self.assertEqual(g["parent"], "T4")
        self.assertEqual(g["parent_tier"], "sonnet")
        self.assertEqual(lineage["escalations_from_cheap_pins"], {"haiku": 0, "sonnet": 1})

        fb = card["failure_breakdown"]
        self.assertEqual(fb["sonnet"], {"verification": 1})
        self.assertNotIn("frontier", fb)

    def test_history_markdown_renders_lineage_and_failure_sections(self):
        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            kits_root.mkdir()
            _write_kit(kits_root, "lineage-demo-md", LINEAGE_TASKS_MD, LINEAGE_NOTES_MD)
            result = _run_cli(["--history", "--kits-dir", str(kits_root)])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## Escalation lineage", result.stdout)
        self.assertIn("## Failure breakdown", result.stdout)
        self.assertIn("escalations descending from cheap pins", result.stdout)

    def test_history_json_omits_lineage_and_failure_keys_when_absent(self):
        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            kits_root.mkdir()
            _write_kit(kits_root, "no-lineage", CLI_TASKS_MD, CLI_NOTES_MD)
            result = _run_cli(["--history", "--kits-dir", str(kits_root), "--json"])

        self.assertEqual(result.returncode, 0, result.stderr)
        card = json.loads(result.stdout)
        self.assertNotIn("lineage", card)
        self.assertNotIn("failure_breakdown", card)

    def test_single_kit_shows_run_id_when_present(self):
        run_tasks_md = """# TASKS — run-demo (synthetic test fixture)

## Phase 1 — only phase

### R1 — task with a run id
- status: done
- model: haiku
"""
        run_notes_md = ("# NOTES — run-demo (synthetic test fixture)\n\n"
                        "## Outcome ledger\n"
                        "outcome: R1 model=haiku attempts=1 result=pass review=clean "
                        "run=2026-07-26-abcd\n")
        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            kits_root.mkdir()
            _write_kit(kits_root, "run-demo", run_tasks_md, run_notes_md)
            result = _run_cli(["run-demo", "--kits-dir", str(kits_root), "--json"])
        self.assertEqual(result.returncode, 0, result.stderr)
        card = json.loads(result.stdout)
        self.assertEqual(card["tasks"][0]["run"], "2026-07-26-abcd")

        with tempfile.TemporaryDirectory() as td2:
            kits_root2 = Path(td2) / "kits"
            kits_root2.mkdir()
            _write_kit(kits_root2, "run-demo-md", run_tasks_md, run_notes_md)
            md_result = _run_cli(["run-demo-md", "--kits-dir", str(kits_root2)])
        self.assertEqual(md_result.returncode, 0, md_result.stderr)
        self.assertIn("Run |", md_result.stdout)
        self.assertIn("2026-07-26-abcd", md_result.stdout)


# ---- T11 (PLAN D11): escalation-rate alarm ----------------------------------------------------


class KitEscalationRateTests(unittest.TestCase):
    def test_zero_with_outcome_is_none(self):
        self.assertIsNone(
            rs._kit_escalation_rate({"kit": "x", "with_outcome": 0, "escalated_pass": 0}))

    def test_missing_keys_treated_as_zero_and_none(self):
        self.assertIsNone(rs._kit_escalation_rate({"kit": "x"}))

    def test_nonzero_with_outcome_computes_rate(self):
        self.assertAlmostEqual(
            rs._kit_escalation_rate({"kit": "x", "with_outcome": 10, "escalated_pass": 3}),
            0.3, places=9)


class BuildEscalationAlarmTests(unittest.TestCase):
    """Direct, pure-function tests (no subprocess) for build_escalation_alarm — the
    acceptance criteria named in T11's brief: sparse history degrades honestly, a stable
    fixture never trips, a spiking one always does, and a kit with no computable rate is
    reported by name, never folded into "no escalations"."""

    def test_zero_snapshots_insufficient(self):
        alarm = rs.build_escalation_alarm([])
        self.assertFalse(alarm["evaluated"])
        self.assertIn("insufficient history", alarm["insufficient_reason"])
        self.assertIsNone(alarm["latest_date"])
        self.assertEqual(alarm["tripped"], [])

    def test_one_snapshot_insufficient(self):
        card = {"kits": [{"kit": "a", "with_outcome": 10, "escalated_pass": 1}]}
        alarm = rs.build_escalation_alarm([("2026-01-01", card)])
        self.assertFalse(alarm["evaluated"])
        self.assertEqual(alarm["latest_date"], "2026-01-01")

    def test_fewer_than_two_pooled_kits_insufficient(self):
        day1 = {"kits": [{"kit": "a", "with_outcome": 10, "escalated_pass": 1}]}
        day2 = {"kits": [{"kit": "a", "with_outcome": 10, "escalated_pass": 1},
                         {"kit": "b", "with_outcome": 5, "escalated_pass": 4}]}
        alarm = rs.build_escalation_alarm([("2026-01-01", day1), ("2026-01-02", day2)])
        self.assertFalse(alarm["evaluated"])
        self.assertIn("kits with a computable escalation rate", alarm["insufficient_reason"])

    def test_stable_fixture_never_trips(self):
        day1 = {"kits": [{"kit": "a", "with_outcome": 10, "escalated_pass": 1},
                         {"kit": "b", "with_outcome": 10, "escalated_pass": 1}]}
        day2 = {"kits": [{"kit": "a", "with_outcome": 10, "escalated_pass": 1},
                         {"kit": "b", "with_outcome": 10, "escalated_pass": 1}]}
        alarm = rs.build_escalation_alarm([("2026-01-01", day1), ("2026-01-02", day2)])
        self.assertTrue(alarm["evaluated"])
        self.assertEqual(alarm["tripped"], [])
        self.assertAlmostEqual(alarm["baseline"]["mean"], 0.1, places=9)
        self.assertAlmostEqual(alarm["baseline"]["stdev"], 0.0, places=9)

    def test_spiking_fixture_always_trips(self):
        day1 = {"kits": [{"kit": "a", "with_outcome": 10, "escalated_pass": 1},
                         {"kit": "b", "with_outcome": 10, "escalated_pass": 1}]}
        day2 = {"kits": [{"kit": "a", "with_outcome": 10, "escalated_pass": 1},
                         {"kit": "b", "with_outcome": 10, "escalated_pass": 1},
                         {"kit": "spike", "with_outcome": 6, "escalated_pass": 5}]}
        alarm = rs.build_escalation_alarm([("2026-01-01", day1), ("2026-01-02", day2)])
        self.assertTrue(alarm["evaluated"])
        self.assertEqual([t["kit"] for t in alarm["tripped"]], ["spike"])
        self.assertAlmostEqual(alarm["tripped"][0]["rate"], 5 / 6, places=9)

    def test_current_kit_with_no_evidence_never_reported_as_zero_escalation(self):
        day1 = {"kits": [{"kit": "a", "with_outcome": 10, "escalated_pass": 1},
                         {"kit": "b", "with_outcome": 10, "escalated_pass": 1}]}
        day2 = {"kits": [{"kit": "a", "with_outcome": 10, "escalated_pass": 1},
                         {"kit": "b", "with_outcome": 10, "escalated_pass": 1},
                         {"kit": "driver-kit", "with_outcome": 0, "escalated_pass": 0}]}
        alarm = rs.build_escalation_alarm([("2026-01-01", day1), ("2026-01-02", day2)])
        self.assertEqual(alarm["no_evidence"], ["driver-kit"])
        self.assertEqual(alarm["tripped"], [])

    def test_kit_reappearing_unchanged_pools_once_not_once_per_snapshot(self):
        day0 = {"kits": [{"kit": "a", "with_outcome": 10, "escalated_pass": 1}]}
        day1 = {"kits": [{"kit": "a", "with_outcome": 10, "escalated_pass": 1}]}
        day2 = {"kits": [{"kit": "a", "with_outcome": 10, "escalated_pass": 1}]}
        alarm = rs.build_escalation_alarm(
            [("2026-01-01", day0), ("2026-01-02", day1), ("2026-01-03", day2)])
        # "a" reappears in BOTH trailing snapshots (day0, day1) -- still one pooled kit,
        # so this stays insufficient rather than accidentally clearing the >=2 floor.
        self.assertFalse(alarm["evaluated"])
        self.assertEqual(alarm["baseline"]["kits"], 1)

    def test_sigma_is_derived_from_data_not_a_hardcoded_percentage(self):
        day1 = {"kits": [{"kit": "a", "with_outcome": 10, "escalated_pass": 1},
                         {"kit": "b", "with_outcome": 10, "escalated_pass": 3}]}
        day2 = {"kits": [{"kit": "a", "with_outcome": 10, "escalated_pass": 1},
                         {"kit": "b", "with_outcome": 10, "escalated_pass": 3}]}
        low = rs.build_escalation_alarm([("2026-01-01", day1), ("2026-01-02", day2)], sigma=0.0)
        high = rs.build_escalation_alarm([("2026-01-01", day1), ("2026-01-02", day2)], sigma=5.0)
        self.assertLess(low["baseline"]["threshold"], high["baseline"]["threshold"])
        # sigma=0 -> b's rate (0.3) exceeds the bare mean (0.2) -> trips; a wide sigma
        # never trips the same fixture -- the SAME data produces different verdicts only
        # because the caller-supplied multiplier changed, never a baked-in percentage.
        self.assertEqual([t["kit"] for t in low["tripped"]], ["b"])
        self.assertEqual(high["tripped"], [])


class TrendAlarmSectionAlwaysRendersTests(unittest.TestCase):
    def test_trend_markdown_always_shows_alarm_heading(self):
        with tempfile.TemporaryDirectory() as td:
            snap = Path(td) / "snap"
            result = _run_cli(["--history", "--trend", "--snapshot-dir", str(snap)])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("## Escalation-rate alarm", result.stdout)
            self.assertIn("insufficient history", result.stdout)

    def test_trend_json_always_carries_escalation_alarm_key(self):
        with tempfile.TemporaryDirectory() as td:
            snap = Path(td) / "snap"
            result = _run_cli(["--history", "--trend", "--snapshot-dir", str(snap), "--json"])
            self.assertEqual(result.returncode, 0, result.stderr)
            card = json.loads(result.stdout)
            self.assertIn("escalation_alarm", card)
            self.assertFalse(card["escalation_alarm"]["evaluated"])


class AlarmWriterGatingTests(unittest.TestCase):
    """T11: write_trend_alarm fires ONLY from the --history --snapshot --trend combo --
    never from a bare --snapshot and never from a bare --trend (ReadOnlyNonSnapshotTests
    in tests/test_crossrepo_trend.py already proves the latter at the whole-tree level;
    these assert the specific alarm/ subdirectory directly)."""

    def test_bare_snapshot_does_not_write_alarm_state(self):
        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            kits_root.mkdir()
            _write_kit(kits_root, "solo", CLI_TASKS_MD, CLI_NOTES_MD)
            snap = Path(td) / "snap"
            result = _run_cli(["--history", "--kits-dir", str(kits_root),
                               "--snapshot", "--snapshot-dir", str(snap), "--json"])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((snap / "alarm").exists())

    def test_bare_trend_does_not_write_alarm_state(self):
        with tempfile.TemporaryDirectory() as td:
            snap = Path(td) / "snap"
            rs.write_snapshot({"kits": [], "tiers": {}}, snap, "2026-03-01")
            rs.write_snapshot({"kits": [], "tiers": {}}, snap, "2026-03-02")
            result = _run_cli(["--history", "--trend", "--snapshot-dir", str(snap), "--json"])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((snap / "alarm").exists())

    def test_snapshot_plus_trend_writes_alarm_state(self):
        with tempfile.TemporaryDirectory() as td:
            kits_root = Path(td) / "kits"
            kits_root.mkdir()
            _write_kit(kits_root, "solo", CLI_TASKS_MD, CLI_NOTES_MD)
            snap = Path(td) / "snap"
            rs.write_snapshot(
                {"kits": [{"kit": "solo", "with_outcome": 2, "escalated_pass": 0}],
                 "tiers": {}}, snap, "2026-03-01")
            result = _run_cli(["--history", "--kits-dir", str(kits_root),
                               "--snapshot", "--snapshot-dir", str(snap),
                               "--trend", "--json"])
            self.assertEqual(result.returncode, 0, result.stderr)
            state_path = snap / "alarm" / "state.json"
            self.assertTrue(state_path.is_file())
            alarm = json.loads(state_path.read_text())
            self.assertIn("evaluated", alarm)

    def test_alarm_state_file_never_confused_with_a_dated_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            snap = Path(td) / "snap"
            rs.write_snapshot({"kits": [], "tiers": {}}, snap, "2026-04-01")
            rs.write_trend_alarm({"evaluated": False}, snap)
            dated_cards, notes = rs.read_snapshots(snap)
            self.assertEqual(len(dated_cards), 1)
            self.assertFalse(any("rogue" in n for n in notes))


class DemoAlarmTests(unittest.TestCase):
    """T11 / Phase 1 F7: the new `--demo --alarm` path -- exercises the alarm trip AND the
    lineage + failure-breakdown sections no prior --demo path touched, without altering
    run_demo's or run_history_demo's own fixtures or goldens."""

    def test_demo_alarm_trend_trips_and_flags_no_evidence(self):
        result = _run_cli(["--demo", "--alarm", "--json"])
        self.assertEqual(result.returncode, 0, result.stderr)
        card = json.loads(result.stdout)
        alarm = card["escalation_alarm"]
        self.assertTrue(alarm["evaluated"])
        tripped_kits = [t["kit"] for t in alarm["tripped"]]
        self.assertTrue(any("spike-3" in k for k in tripped_kits))
        self.assertTrue(any("driver-blind" in k for k in alarm["no_evidence"]))

    def test_demo_alarm_history_shows_lineage_and_failure_sections(self):
        result = _run_cli(["--demo", "--alarm", "--history"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## Escalation lineage", result.stdout)
        self.assertIn("## Failure breakdown", result.stdout)
        self.assertIn("Tier = the IMPLEMENTER's dispatch tier", result.stdout)

    def test_demo_alarm_rejects_live_and_by_task(self):
        for flag in ("--live", "--by-task"):
            result = _run_cli(["--demo", "--alarm", flag])
            self.assertNotEqual(result.returncode, 0)

    def test_demo_alone_and_demo_history_alone_unaffected(self):
        # The exhaustive byte-stability check lives in T2GoldenByteStabilityTests above;
        # this is an extra regression signal specific to --alarm's own wiring.
        d = _run_cli(["--demo"])
        h = _run_cli(["--demo", "--history"])
        self.assertEqual(d.returncode, 0, d.stderr)
        self.assertEqual(h.returncode, 0, h.stderr)
        self.assertNotIn("Escalation-rate alarm", d.stdout)
        self.assertNotIn("Escalation-rate alarm", h.stdout)
        self.assertEqual(d.stdout, GOLDEN_DEMO_MARKDOWN)
        self.assertEqual(h.stdout, GOLDEN_DEMO_HISTORY_MARKDOWN)


# ---- U4 envelope (PLAN E3) -----------------------------------------------------------

# A synthetic pricing dict carrying all FOUR LIVE_TIER_ORDER tiers plus task_profiles (P
# above deliberately has no opus model and no task_profiles, since no test before U4 needed
# either) -- fake ids, round rates, one task profile ("S", matching ENVELOPE_TASK_PROFILE's
# default so price_envelope_class's un-parametrized envelope_call_cost calls find it) sized
# so the arithmetic below is hand-checkable: cost per call = 0.04*input_per_mtok +
# 0.004*output_per_mtok (40000 input / 4000 output tokens, the same shape as pricing.json's
# real "S").
ENV_P = {
    "cached_date": "2020-01-01",
    "billing_mode": "api",
    "cache_read_multiplier": 0.1,
    "cache_write_multiplier_5m": 1.25,
    "models": {
        "fake-haiku-1": {"display": "Fake Haiku", "tier": "haiku",
                          "input_per_mtok": 1.0, "output_per_mtok": 5.0},
        "fake-sonnet-1": {"display": "Fake Sonnet", "tier": "sonnet",
                           "input_per_mtok": 3.0, "output_per_mtok": 15.0},
        "fake-opus-1": {"display": "Fake Opus", "tier": "opus",
                         "input_per_mtok": 5.0, "output_per_mtok": 25.0},
        "fake-frontier-1": {"display": "Fake Frontier", "tier": "frontier",
                             "input_per_mtok": 10.0, "output_per_mtok": 50.0},
    },
    "task_profiles": {
        "S": {"label": "test profile", "input_tokens": 40000, "output_tokens": 4000},
    },
}
# Hand-computed per-tier call costs under ENV_P's "T" profile (0.04*input + 0.004*output):
ENV_CALL_COST = {"haiku": 0.06, "sonnet": 0.18, "opus": 0.3, "frontier": 0.6}


def _member(kit="k1", task="X1", resolved=False, resolved_tier=None):
    return {"kit": kit, "task": task, "resolved": resolved, "resolved_tier": resolved_tier}


class EnvelopeCallCostTests(unittest.TestCase):
    def test_prices_from_task_profile_via_cr_price(self):
        cost = rs.envelope_call_cost(ENV_P, "sonnet", profile="S")
        self.assertAlmostEqual(cost, ENV_CALL_COST["sonnet"])

    def test_unknown_profile_returns_none(self):
        self.assertIsNone(rs.envelope_call_cost(ENV_P, "haiku", profile="does-not-exist"))

    def test_tier_with_no_model_returns_none(self):
        # P (module fixture) carries no opus model.
        self.assertIsNone(rs.envelope_call_cost(P, "opus", profile="S"))

    def test_default_profile_is_module_constant(self):
        cost = rs.envelope_call_cost(ENV_P, "haiku")
        expected = rs.envelope_call_cost(ENV_P, "haiku", profile=rs.ENVELOPE_TASK_PROFILE)
        self.assertEqual(cost, expected)


class DeriveEnvelopeClassesTests(unittest.TestCase):
    def test_blocked_outcome_is_an_unresolved_member(self):
        tasks = [_task("T1", model="sonnet")]
        outcomes = {"T1": {"model": "sonnet", "attempts": 2, "result": "blocked",
                            "review": "none", "failure": "verification"}}
        records = [_rec("k1", tasks, outcomes)]
        classes, notes = rs.derive_envelope_classes(records)
        self.assertEqual(notes, [])
        self.assertEqual(list(classes.keys()), [("sonnet", "verification")])
        members = classes[("sonnet", "verification")]
        self.assertEqual(members, [_member("k1", "T1", resolved=False, resolved_tier=None)])

    def test_escalated_pass_resolves_at_the_fixer_tier_named_on_its_own_line(self):
        tasks = [_task("T1", model="haiku")]
        outcomes = {"T1": {"model": "fable", "attempts": 3, "result": "escalated-pass",
                            "review": "clean", "failure": "execution"}}
        records = [_rec("k1", tasks, outcomes)]
        classes, notes = rs.derive_envelope_classes(records)
        self.assertEqual(notes, [])
        members = classes[("haiku", "execution")]
        self.assertEqual(members, [_member("k1", "T1", resolved=True,
                                            resolved_tier="frontier")])

    def test_escalated_pass_origin_reflects_applied_reroute(self):
        # effective_alias: the task's raw pin is haiku, but an APPLIED reroute to sonnet
        # covers it -- the class's origin tier must be the reconstructed DISPATCH tier
        # (sonnet), not the raw pin, mirroring history_tier_stats/build_failure_breakdown.
        tasks = [_task("T1", model="haiku")]
        outcomes = {"T1": {"model": "fable", "attempts": 2, "result": "escalated-pass",
                            "review": "clean", "failure": "execution"}}
        events = [{"mode": "applied", "from": "haiku", "to": "sonnet", "tasks": ["T1"]}]
        records = [_rec("k1", tasks, outcomes, events)]
        classes, notes = rs.derive_envelope_classes(records)
        self.assertEqual(notes, [])
        self.assertEqual(list(classes.keys()), [("sonnet", "execution")])

    def test_parent_carrying_outcome_excluded(self):
        tasks = [_task("T4", model="sonnet"), _task("T7", model="fable")]
        outcomes = {
            "T4": {"model": "sonnet", "attempts": 2, "result": "blocked", "review": "none",
                   "failure": "verification"},
            "T7": {"model": "fable", "attempts": 3, "result": "escalated-pass",
                   "review": "clean", "parent": "T4", "failure": "verification"},
        }
        records = [_rec("k1", tasks, outcomes)]
        classes, notes = rs.derive_envelope_classes(records)
        members = classes[("sonnet", "verification")]
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0]["task"], "T4")

    def test_failure_on_plain_pass_is_out_of_grammar(self):
        tasks = [_task("T1", model="sonnet")]
        outcomes = {"T1": {"model": "sonnet", "attempts": 1, "result": "pass",
                            "review": "clean", "failure": "execution"}}
        records = [_rec("k1", tasks, outcomes)]
        classes, notes = rs.derive_envelope_classes(records)
        self.assertEqual(classes, {})
        self.assertTrue(any("out of grammar" in n for n in notes))

    def test_unknown_task_id_noted_and_skipped(self):
        outcomes = {"GHOST": {"model": "sonnet", "attempts": 1, "result": "blocked",
                               "review": "none", "failure": "execution"}}
        records = [_rec("k1", [], outcomes)]
        classes, notes = rs.derive_envelope_classes(records)
        self.assertEqual(classes, {})
        self.assertTrue(any("unknown task id" in n and "GHOST" in n for n in notes))

    def test_resolved_tier_below_origin_is_noted_and_treated_as_unresolved(self):
        # P3-F8: an escalated-pass naming a model BELOW its own dispatch tier is out of
        # grammar (the ladder never walks downward). It used to reach price_envelope_class
        # and crash there with ValueError: tuple.index(x): x not in tuple, destroying the
        # whole report. It must note-and-degrade like its four sibling bad-data shapes.
        tasks = [_task("T1", model="opus")]
        outcomes = {"T1": {"model": "haiku", "attempts": 2, "result": "escalated-pass",
                            "review": "clean", "failure": "execution"}}
        records = [_rec("k1", tasks, outcomes)]
        classes, notes = rs.derive_envelope_classes(records)
        members = classes[("opus", "execution")]
        self.assertEqual(members, [_member("k1", "T1", resolved=False, resolved_tier=None)])
        self.assertTrue(any("BELOW its origin tier" in n for n in notes), notes)

    def test_malformed_below_origin_line_does_not_destroy_the_report(self):
        # The same shape end-to-end through build_envelope/render: a note, a priced row for
        # the surviving evidence, and no traceback.
        tasks = [_task("T1", model="opus"), _task("T2", model="opus")]
        outcomes = {
            "T1": {"model": "haiku", "attempts": 2, "result": "escalated-pass",
                   "review": "clean", "failure": "execution"},
            "T2": {"model": "fable", "attempts": 3, "result": "escalated-pass",
                   "review": "clean", "failure": "execution"},
        }
        records = [_rec("k1", tasks, outcomes)]
        evidence = {"tasks_with_outcome": 2, "outcomes_with_failure": 2, "kits_total": 1,
                    "kits_with_session_line": 0, "sessions_found": 0, "sessions_priced": 0}
        card = rs.build_envelope("kits", records, evidence, ENV_P, [])
        self.assertEqual(len(card["classes"]), 1)
        row = card["classes"][0]
        self.assertEqual((row["n"], row["resolved"], row["blocked"]), (2, 1, 1))
        self.assertTrue(any("BELOW its origin tier" in n for n in card["notes"]),
                        card["notes"])
        md = rs.render_envelope_markdown(card)
        self.assertIn("opus × execution", md)
        self.assertIn("BELOW its origin tier", md)

    def test_no_failure_evidence_anywhere_returns_empty(self):
        tasks = [_task("A1", model="haiku")]
        outcomes = {"A1": {"model": "haiku", "attempts": 1, "result": "pass",
                            "review": "clean"}}
        records = [_rec("k1", tasks, outcomes)]
        classes, notes = rs.derive_envelope_classes(records)
        self.assertEqual((classes, notes), ({}, []))


class PriceEnvelopeClassTests(unittest.TestCase):
    def test_all_resolve_at_top_tier_makes_cascade_cheaper(self):
        # Every member needs the full walk to frontier -- the ladder pays for every doomed
        # intermediate rung, the cascade skips straight there.
        members = [_member(task=f"X{i}", resolved=True, resolved_tier="frontier")
                   for i in range(10)]
        row, note = rs.price_envelope_class("haiku", "execution", members, ENV_P)
        self.assertIsNone(note)
        c = ENV_CALL_COST
        expected_observed = 10 * (c["haiku"] + c["sonnet"] + c["opus"] + c["frontier"])
        expected_cascade = 10 * (c["haiku"] + c["frontier"])
        self.assertAlmostEqual(row["observed_ladder_usd"], expected_observed)
        self.assertAlmostEqual(row["cascade_usd"], expected_cascade)
        self.assertEqual(row["cascade_second_tier"], "frontier")
        self.assertLess(row["cascade_usd"], row["observed_ladder_usd"])
        self.assertGreater(row["savings_usd"], 0)

    def test_all_resolve_at_next_rung_makes_ladder_cheaper(self):
        # Every member resolves one rung up (sonnet) -- the ladder never pays for opus or
        # frontier at all, while a two-model cascade whose second tier must be >= the
        # highest-needed tier (sonnet here) still has to pay sonnet for everyone, so the two
        # sides tie UNLESS a higher outlier forces the cascade past what most members needed
        # (proven by the mixed test below); on its own this case is at best a tie.
        members = [_member(task=f"X{i}", resolved=True, resolved_tier="sonnet")
                   for i in range(10)]
        row, note = rs.price_envelope_class("haiku", "execution", members, ENV_P)
        self.assertIsNone(note)
        c = ENV_CALL_COST
        expected = 10 * (c["haiku"] + c["sonnet"])
        self.assertAlmostEqual(row["observed_ladder_usd"], expected)
        self.assertAlmostEqual(row["cascade_usd"], expected)
        self.assertEqual(row["cascade_second_tier"], "sonnet")

    def test_rare_middle_resolution_cascade_cheaper(self):
        # 1 of 10 resolves at sonnet, 9 need frontier -- mirrors DEMO_ENVELOPE_RARE.
        members = ([_member(task="R1", resolved=True, resolved_tier="sonnet")]
                   + [_member(task=f"R{i}", resolved=True, resolved_tier="frontier")
                      for i in range(2, 11)])
        row, note = rs.price_envelope_class("haiku", "execution", members, ENV_P)
        self.assertIsNone(note)
        self.assertGreater(row["savings_usd"], 0)  # cascade cheaper
        self.assertEqual(row["cascade_second_tier"], "frontier")

    def test_frequent_middle_resolution_ladder_cheaper(self):
        # 9 of 10 resolve at sonnet, 1 needs frontier -- mirrors DEMO_ENVELOPE_OFTEN.
        members = ([_member(task=f"O{i}", resolved=True, resolved_tier="sonnet")
                    for i in range(1, 10)]
                   + [_member(task="O10", resolved=True, resolved_tier="frontier")])
        row, note = rs.price_envelope_class("haiku", "verification", members, ENV_P)
        self.assertIsNone(note)
        self.assertLess(row["savings_usd"], 0)  # cascade MORE expensive -> ladder cheaper
        self.assertEqual(row["cascade_second_tier"], "frontier")

    def test_unpriceable_tier_returns_none_with_note(self):
        members = [_member(resolved=True, resolved_tier="opus")]
        row, note = rs.price_envelope_class("haiku", "execution", members, P)  # P has no opus
        self.assertIsNone(row)
        self.assertIn("could not be priced", note)

    def test_origin_at_top_of_ladder_collapses_cascade_to_ladder(self):
        members = [_member(resolved=False, resolved_tier=None)]
        row, note = rs.price_envelope_class("frontier", "execution", members, ENV_P)
        self.assertIsNone(note)
        self.assertIsNone(row["cascade_second_tier"])
        self.assertEqual(row["cascade_usd"], row["observed_ladder_usd"])
        self.assertEqual(row["savings_usd"], 0)

    def test_per_tier_resolution_rates_are_conditional_on_reaching(self):
        members = ([_member(task="a", resolved=True, resolved_tier="sonnet")] * 9
                   + [_member(task="b", resolved=True, resolved_tier="frontier")])
        row, note = rs.price_envelope_class("haiku", "execution", members, ENV_P)
        self.assertIsNone(note)
        ptr = row["per_tier_resolution"]
        self.assertEqual(ptr["haiku"], {"reaching": 10, "resolved": 0, "rate": 0.0})
        self.assertEqual(ptr["sonnet"], {"reaching": 10, "resolved": 9, "rate": 0.9})
        self.assertEqual(ptr["opus"], {"reaching": 1, "resolved": 0, "rate": 0.0})
        self.assertEqual(ptr["frontier"], {"reaching": 1, "resolved": 1, "rate": 1.0})

    def test_resolution_at_the_origin_tier_is_counted_and_leaves_remaining(self):
        # P3-F7: a member whose resolved_tier IS its origin tier used to be counted in the
        # row's "resolved" but hard-zeroed out of the per-tier table AND never removed from
        # remaining -- so the table under-counted the row and every higher rung's conditional
        # rate ran over an inflated denominator (frontier's true 2/2 printed as 2/3 = 67%).
        members = [_member(task="M1", resolved=True, resolved_tier="opus"),
                   _member(task="M2", resolved=True, resolved_tier="frontier"),
                   _member(task="M3", resolved=True, resolved_tier="frontier")]
        row, note = rs.price_envelope_class("opus", "execution", members, ENV_P)
        self.assertIsNone(note)
        ptr = row["per_tier_resolution"]
        self.assertEqual(ptr["opus"], {"reaching": 3, "resolved": 1,
                                       "rate": 1 / 3})
        self.assertEqual(ptr["frontier"], {"reaching": 2, "resolved": 2, "rate": 1.0})
        # The table now sums to the row's own Resolved column -- the invariant that failed.
        self.assertEqual(sum(s["resolved"] for s in ptr.values()), row["resolved"])
        self.assertEqual(row["resolved"], 3)

    def test_origin_tier_resolver_is_not_billed_a_second_cascade_hop(self):
        # P3-F7 (cost half): the origin-resolved member never needed a second call, so
        # neither side may charge it one. Ladder: 1 origin call for M1, origin+frontier for
        # the other two. Cascade: the same single call for M1, origin+frontier for the two
        # that actually escalated -- here the two sides tie exactly.
        members = [_member(task="M1", resolved=True, resolved_tier="opus"),
                   _member(task="M2", resolved=True, resolved_tier="frontier"),
                   _member(task="M3", resolved=True, resolved_tier="frontier")]
        row, note = rs.price_envelope_class("opus", "execution", members, ENV_P)
        self.assertIsNone(note)
        c = ENV_CALL_COST
        self.assertAlmostEqual(row["observed_ladder_usd"],
                               3 * c["opus"] + 2 * c["frontier"])
        self.assertAlmostEqual(row["cascade_usd"], 3 * c["opus"] + 2 * c["frontier"])
        self.assertEqual(row["cascade_second_tier"], "frontier")
        self.assertAlmostEqual(row["savings_usd"], 0.0)

    def test_every_member_resolving_at_origin_fires_no_second_rung(self):
        # Nobody escalated, so a two-model cascade never reaches its second model at all:
        # no tier is named (naming one would imply a dispatch history never records) and the
        # two sides cost exactly the same single call per member.
        members = [_member(task=f"S{i}", resolved=True, resolved_tier="sonnet")
                   for i in range(4)]
        row, note = rs.price_envelope_class("sonnet", "execution", members, ENV_P)
        self.assertIsNone(note)
        self.assertIsNone(row["cascade_second_tier"])
        self.assertAlmostEqual(row["observed_ladder_usd"], 4 * ENV_CALL_COST["sonnet"])
        self.assertAlmostEqual(row["cascade_usd"], 4 * ENV_CALL_COST["sonnet"])
        self.assertEqual(row["savings_usd"], 0)
        ptr = row["per_tier_resolution"]
        self.assertEqual(ptr["sonnet"], {"reaching": 4, "resolved": 4, "rate": 1.0})
        self.assertEqual(ptr["opus"], {"reaching": 0, "resolved": 0, "rate": None})


class BuildRenderEnvelopeTests(unittest.TestCase):
    def test_build_envelope_zero_classes_declines(self):
        tasks = [_task("A1", model="haiku")]
        outcomes = {"A1": {"model": "haiku", "attempts": 1, "result": "pass",
                            "review": "clean"}}
        records = [_rec("k1", tasks, outcomes)]
        evidence = {"tasks_with_outcome": 1, "outcomes_with_failure": 0, "kits_total": 1,
                    "kits_with_session_line": 0, "sessions_found": 0, "sessions_priced": 0}
        card = rs.build_envelope("kits", records, evidence, ENV_P, [])
        self.assertEqual(card["classes"], [])
        self.assertEqual(card["evidence"], evidence)
        md = rs.render_envelope_markdown(card)
        self.assertIn("Unanswerable from this repo's history today", md)
        self.assertIn("0/1 outcomes carry it", md)
        self.assertNotIn("## Per-class", md)

    def test_build_envelope_with_classes_renders_table_and_est_label(self):
        tasks = [_task(f"X{i}", model="haiku") for i in range(1, 3)]
        outcomes = {
            "X1": {"model": "fable", "attempts": 3, "result": "escalated-pass",
                   "review": "clean", "failure": "execution"},
            "X2": {"model": "sonnet", "attempts": 2, "result": "escalated-pass",
                   "review": "clean", "failure": "execution"},
        }
        records = [_rec("k1", tasks, outcomes)]
        evidence = {"tasks_with_outcome": 2, "outcomes_with_failure": 2, "kits_total": 1,
                    "kits_with_session_line": 0, "sessions_found": 0, "sessions_priced": 0}
        card = rs.build_envelope("kits", records, evidence, ENV_P, [])
        self.assertEqual(len(card["classes"]), 1)
        md = rs.render_envelope_markdown(card)
        self.assertIn("## Per-class ladder vs. cascade (est.)", md)
        self.assertIn("## Per-tier resolution rate", md)
        self.assertIn("`est.`", md)
        self.assertIn("haiku × execution", md)

    def test_classes_sorted_by_ladder_position_then_failure(self):
        tasks = [_task("S1", model="sonnet"), _task("H1", model="haiku")]
        outcomes = {
            "S1": {"model": "sonnet", "attempts": 1, "result": "blocked", "review": "none",
                   "failure": "verification"},
            "H1": {"model": "haiku", "attempts": 1, "result": "blocked", "review": "none",
                   "failure": "coherence"},
        }
        records = [_rec("k1", tasks, outcomes)]
        evidence = {"tasks_with_outcome": 2, "outcomes_with_failure": 2, "kits_total": 1,
                    "kits_with_session_line": 0, "sessions_found": 0, "sessions_priced": 0}
        card = rs.build_envelope("kits", records, evidence, ENV_P, [])
        origins = [(r["origin_tier"], r["failure"]) for r in card["classes"]]
        self.assertEqual(origins, [("haiku", "coherence"), ("sonnet", "verification")])


ENV_CLI_NOTES_MD = """# NOTES — env-cli (synthetic test fixture)

## Outcome ledger
outcome: E1 model=fable attempts=3 result=escalated-pass review=clean failure=execution
outcome: E2 model=sonnet attempts=2 result=blocked review=none failure=coherence
outcome: E3 model=sonnet attempts=2 result=blocked review=none
"""


class CliEnvelopeEndToEndTests(unittest.TestCase):
    """CLI-level tests over the real pricing.json (never a real ~/.claude project store —
    every --projects-dir below is a fresh empty temp dir, mirroring CliEndToEndTests)."""

    def test_demo_envelope_proves_both_cascade_directions(self):
        result = _run_cli(["--demo", "--envelope", "--json"])
        self.assertEqual(result.returncode, 0, result.stderr)
        card = json.loads(result.stdout)
        self.assertEqual(card["evidence"]["outcomes_with_failure"], 20)
        by_failure = {c["failure"]: c for c in card["classes"]}
        self.assertGreater(by_failure["execution"]["savings_usd"], 0)     # cascade cheaper
        self.assertLess(by_failure["verification"]["savings_usd"], 0)    # ladder cheaper

    def test_demo_envelope_markdown_names_both_directions(self):
        result = _run_cli(["--demo", "--envelope"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("haiku × execution", result.stdout)
        self.assertIn("haiku × verification", result.stdout)
        self.assertIn("`est.`", result.stdout)

    def test_real_kits_dir_with_no_failure_evidence_declines(self):
        with tempfile.TemporaryDirectory() as tmp:
            kits = Path(tmp) / "kits"
            _write_kit(kits, "cli-e2e", CLI_TASKS_MD, CLI_NOTES_MD)  # no failure= anywhere
            proj = Path(tmp) / "projects"
            proj.mkdir()
            result = _run_cli(["--history", "--envelope", "--kits-dir", str(kits),
                                "--projects-dir", str(proj), "--no-subagents", "--json"])
            self.assertEqual(result.returncode, 0, result.stderr)
            card = json.loads(result.stdout)
            self.assertEqual(card["classes"], [])
            self.assertEqual(card["evidence"]["outcomes_with_failure"], 0)
            self.assertEqual(card["evidence"]["tasks_with_outcome"], 3)
            self.assertEqual(card["evidence"]["kits_total"], 1)

    def test_real_kits_dir_with_failure_evidence_prices_classes(self):
        with tempfile.TemporaryDirectory() as tmp:
            kits = Path(tmp) / "kits"
            tasks_md = ("# TASKS — env-cli (synthetic test fixture)\n\n"
                        "## Phase 1 — only phase\n\n"
                        "### E1 — a\n- status: done\n- model: haiku\n\n"
                        "### E2 — b\n- status: blocked\n- model: sonnet\n\n"
                        "### E3 — c\n- status: blocked\n- model: sonnet\n")
            _write_kit(kits, "env-cli", tasks_md, ENV_CLI_NOTES_MD)
            proj = Path(tmp) / "projects"
            proj.mkdir()
            result = _run_cli(["--history", "--envelope", "--kits-dir", str(kits),
                                "--projects-dir", str(proj), "--no-subagents", "--json"])
            self.assertEqual(result.returncode, 0, result.stderr)
            card = json.loads(result.stdout)
            self.assertEqual(card["evidence"]["outcomes_with_failure"], 2)
            self.assertEqual(len(card["classes"]), 2)
            by_failure = {c["failure"]: c for c in card["classes"]}
            self.assertEqual(by_failure["execution"]["origin_tier"], "haiku")
            self.assertTrue(by_failure["execution"]["resolved"])
            self.assertEqual(by_failure["coherence"]["origin_tier"], "sonnet")
            self.assertEqual(by_failure["coherence"]["blocked"], 1)

    def test_envelope_alone_requires_history_unless_demo(self):
        result = _run_cli(["--envelope"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("rides --history", result.stderr)

    def test_envelope_rejects_live_by_task_alarm_snapshot_trend_session(self):
        base = ["--history", "--envelope"]
        for extra in (["--live"], ["--by-task"], ["--session", "SESS"],
                      ["--snapshot"], ["--trend"]):
            result = _run_cli(base + extra)
            self.assertNotEqual(result.returncode, 0, extra)
        result = _run_cli(["--demo", "--envelope", "--alarm"])
        self.assertNotEqual(result.returncode, 0)

    def test_envelope_rejects_multiple_kits_dir(self):
        result = _run_cli(["--history", "--envelope",
                            "--kits-dir", ".", "--kits-dir", "."])
        self.assertNotEqual(result.returncode, 0)

    def test_demo_and_demo_history_goldens_unaffected(self):
        d = _run_cli(["--demo"])
        h = _run_cli(["--demo", "--history"])
        self.assertEqual(d.stdout, GOLDEN_DEMO_MARKDOWN)
        self.assertEqual(h.stdout, GOLDEN_DEMO_HISTORY_MARKDOWN)

    def test_writes_nothing_read_only(self):
        # Mirrors ReadOnlyProofTests' contract for the new mode: a temp kits dir's mtime and
        # membership are unchanged after --history --envelope runs against it.
        with tempfile.TemporaryDirectory() as tmp:
            kits = Path(tmp) / "kits"
            _write_kit(kits, "cli-e2e", CLI_TASKS_MD, CLI_NOTES_MD)
            proj = Path(tmp) / "projects"
            proj.mkdir()
            before = sorted(p.name for p in kits.rglob("*"))
            result = _run_cli(["--history", "--envelope", "--kits-dir", str(kits),
                                "--projects-dir", str(proj), "--no-subagents"])
            self.assertEqual(result.returncode, 0, result.stderr)
            after = sorted(p.name for p in kits.rglob("*"))
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
