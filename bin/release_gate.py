#!/usr/bin/env python3
"""The release gate: what this repository may claim about each harness, computed from the
artifacts that carry the evidence and never typed by hand.

Roadmap step 26. Every earlier step left a record behind -- a capability row with a date, a
contract version constant, a test that drives a driver through a stub, a pricing file with a
`cached_date`, an ignore rule for a private store. Until now nothing read those records
together, so the documentation could say "supported" where the registry says `unknown`, a
store could be added without its ignore rule and nobody would notice until it was committed,
and a passing suite could be quoted as if a vendor's client had been run. This module is the
ONE place that assembles the release matrix, the shared-contract evidence table, the packaging
review, the checklist, the migration notes, and the re-evaluation procedure, and the marked
block of `docs/RELEASE.md` is its render.

THE DISTINCTION THIS FILE EXISTS TO KEEP. Two columns, never merged:

  - STUB CONFORMANCE: a named test drove a driver through a stub executable and a temp store
    and the shared contract held. That is evidence about polytropos's code.
  - INSTALLED-CLIENT VERIFICATION: someone ran the vendor's client on a date and recorded it
    in `primitives/harness-capabilities.json`. That is evidence about a host.

An argv fixture is not a verified OS sandbox. A green suite says a unit works, not that a
client was run. The registry says which is which, and this gate reports both columns side by
side rather than letting either stand in for the other.

WHAT THIS MODULE DOES NOT DO. It never edits the registry (`reverify` lists what a release
invalidates and says so; the row is corrected by the person who ran the check). It never
promotes a routing default, never installs into a home directory, never spawns a harness
client, and never reads a home directory or a private store. Its only processes are read-only
git verbs through `bin/proc_runner.py` and, on `contracts --run`, this repository's own test
loader in-process. The generated block of `docs/RELEASE.md` is deterministic: nothing in it
depends on the day it was built, the revision, or the host, so a rebuild on a clean tree is a
no-op and `check` can fail on drift.
"""

import argparse
import importlib.util
import io
import json
import re
import sys
import unittest
from contextlib import contextmanager
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = REPO_ROOT / "bin"
TESTS_DIR = REPO_ROOT / "tests"

#: The gate's own contract version, listed beside the others it reports.
GATE_VERSION = "polytropos.release-gate/1"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_DRIFT = 3

#: The one documentation page whose marked block this module writes.
RELEASE_DOC = Path("docs") / "RELEASE.md"
BLOCK_START = "<!-- release-gate:start -->"
BLOCK_END = "<!-- release-gate:end -->"

#: Read-only git verbs this module may run against the repository, and nothing else.
GIT_READ_VERBS = ("rev-parse", "ls-files", "log", "status")

#: The day this gate was introduced. A `verified: supported` row dated on or after it must
#: name the client version it was verified against; earlier rows recorded none and are not
#: rewritten, because backfilling a version nobody wrote down would be hand-authoring evidence.
CLIENT_VERSION_REQUIRED_FROM = "2026-09-13"

#: Registry keys, in the order the matrix lists them. `stub` is the conformance target and is
#: reported like the others so that its "verified" rows are visibly about a stub.
HARNESSES = ("claude-code", "codex", "copilot", "cursor", "stub")
SHARED = "shared"

#: What is known about each harness that the registry does not carry: which driver, which
#: binary flag names the client, where the bundle lives, how it is installed, and the review
#: form the driver pins. Binary names are read from the drivers' own parsers at run time.
HARNESS_FACTS = {
    "claude-code": {
        "label": "Claude Code",
        "driver": "bin/claude_execute.py",
        "binary_flag": "--claude-bin",
        "bundle": "skills/ (the plugin itself)",
        "install": "claude plugin install polytropos@polytropos-local",
        "review_form": "restricted `--allowedTools` profile (never the blanket grant)",
        "eval_adapter": "workflow_eval.claude_adapter",
    },
    "codex": {
        "label": "OpenAI Codex CLI",
        "driver": "bin/codex_execute.py",
        "binary_flag": "--codex-bin",
        "bundle": "codex/",
        "install": "python3 bin/harness_select.py install --harness codex",
        "review_form": "`--sandbox read-only`, extra arguments cannot override it",
        "eval_adapter": "workflow_eval.codex_adapter",
    },
    "copilot": {
        "label": "GitHub Copilot CLI",
        "driver": "bin/copilot_execute.py",
        "binary_flag": "--copilot-bin",
        "bundle": "copilot/.github/",
        "install": "python3 bin/harness_select.py install --harness copilot",
        "review_form": "the reviewer agent without `--allow-all-tools` (no narrower pin exists)",
        "eval_adapter": "workflow_eval.copilot_adapter",
    },
    "cursor": {
        "label": "Cursor CLI",
        "driver": "bin/cursor_execute.py (bin/cursor_adapter.py)",
        "binary_flag": "--cursor-bin",
        "bundle": "cursor/",
        "install": "python3 bin/harness_select.py install --harness cursor --project DIR",
        "review_form": "`--mode ask`, never `--force`",
        "eval_adapter": "workflow_eval.cursor_adapter",
    },
    "stub": {
        "label": "Stub (conformance target; runs nothing)",
        "driver": "bin/harness_adapter.py StubAdapter; bin/kit_scheduler.py StubDispatcher",
        "binary_flag": None,
        "bundle": None,
        "install": None,
        "review_form": "canned result",
        "eval_adapter": "workflow_eval.stub_adapter",
    },
}

#: Which driver module answers for a harness's binary name.
DRIVER_MODULES = {
    "claude-code": "claude_execute",
    "codex": "codex_execute",
    "copilot": "copilot_execute",
    "cursor": "cursor_execute",
}

#: Contract version constants, each read from the module that owns it. A version typed here
#: would rot the day the module bumped it.
VERSION_SOURCES = (
    ("task contract", "kit_contract", "CONTRACT_VERSION"),
    ("adapter contract", "harness_adapter", "ADAPTER_VERSION"),
    ("attempt ledger", "attempt_ledger", "LEDGER_VERSION"),
    ("attempt history", "attempt_history", "HISTORY_VERSION"),
    ("model registry", "model_registry", "REGISTRY_VERSION"),
    ("routing decision", "routing_policy", "CONTRACT_VERSION"),
    ("graph grounding", "graph_ground", "CONTRACT_VERSION"),
    ("graph provenance sidecar", "graph_ground", "SIDECAR_VERSION"),
    ("integration manifest", "kit_scheduler", "MANIFEST_VERSION"),
    ("workflow evaluation", "workflow_eval", "EVAL_VERSION"),
    ("evaluation manifest", "workflow_eval", "MANIFEST_VERSION"),
    ("policy proposal", "workflow_eval", "PROPOSAL_VERSION"),
    ("routing policy file", "workflow_eval", "POLICY_VERSION"),
    ("policy reference block", "workflow_eval", "POLICY_REFS_VERSION"),
    ("policy approval record", "workflow_eval", "APPROVAL_VERSION"),
    ("policy activation pointer", "workflow_eval", "ACTIVATION_VERSION"),
    ("policy evidence report", "workflow_eval", "POLICY_EVIDENCE_VERSION"),
    ("three-arm trial protocol", "workflow_eval", "TRIAL_PROTOCOL_VERSION"),
    ("lessons store", "lessons_store", "SCHEMA"),
    ("protected profile sentinels", "exec_policy", "SENTINEL_VERSION"),
    ("decision contract", "decision_contract", "CONTRACT_VERSION"),
    ("policy bundle", "decision_contract", "BUNDLE_VERSION"),
    ("candidate proposal", "decision_contract", "CANDIDATE_VERSION"),
    ("decision replay record", "decision_provider", "REPLAY_VERSION"),
    ("decision prediction join", "decision_eval", "JOIN_VERSION"),
    ("decision calibration report", "decision_eval", "CALIBRATION_VERSION"),
    ("decision recovery report", "decision_eval", "RECOVERY_REPORT_VERSION"),
    ("context candidate manifest", "decision_context", "CONTEXT_VERSION"),
    ("training snapshot", "training_data", "SNAPSHOT_VERSION"),
    ("training cause taxonomy", "training_data", "TAXONOMY_VERSION"),
    ("training label lifecycle", "training_data", "LIFECYCLE_VERSION"),
)

#: Pricing files, one per harness, never merged. Read for `cached_date` and roster size only.
PRICING_FILES = {
    "claude-code": "data/pricing.json",
    "codex": "data/pricing.codex.json",
    "copilot": "data/pricing.copilot.json",
    "cursor": "data/pricing.cursor.json",
}

# ---- the shared contracts ---------------------------------------------------------------------
#
# Eleven contracts the roadmap names. Each carries the tests that prove it through a stub per
# harness (STUB CONFORMANCE) and the registry rows that would have to be verified on a real
# client for the host side to count (INSTALLED-CLIENT VERIFICATION). A contract with no
# registry row is polytropos's own -- verdict provenance is not a feature any vendor ships --
# and for those the stub column is the whole of the evidence, which the report says.
#
# Test ids are `module.Class.method` under tests/. `check` refuses an id that resolves to no
# test, so this table cannot quietly outlive a rename.

CONTRACTS = (
    {
        "id": "dispatch-failure",
        "title": "Dispatch failure",
        "steps": "07, 19",
        "claim": "a failed, crashed, or refused dispatch is classified and never counted as success; "
                 "an auth, config, permission, or infrastructure failure stops the ladder",
        "capabilities": {"claude-code": ("dispatch",), "codex": ("dispatch",),
                         "copilot": ("dispatch",), "cursor": ("dispatch", "identity_probe"),
                         "stub": ("dispatch",)},
        "tests": {
            "claude-code": (
                "test_claude_execute.DispatchAndReadinessTests.test_a_failed_dispatch_does_not_become_done_on_a_passing_check",
                "test_claude_execute.DispatchAndReadinessTests.test_a_failed_dispatch_does_not_climb_the_escalation_ladder",
                "test_claude_execute.DispatchAndReadinessTests.test_a_runner_that_reports_nothing_is_unknown_not_success",
                "test_claude_execute.DispatchAndReadinessTests.test_verification_failure_after_a_successful_dispatch_still_escalates",
            ),
            "codex": (
                "test_codex_execute_policy.ReservedRecoveryTests.test_dispatch_failure_cannot_become_success_from_passing_verify",
                "test_codex_execute_policy.ReservedRecoveryTests.test_runner_oserror_becomes_audited_failure",
                "test_codex_execute_policy.ReservedRecoveryTests.test_runtime_policy_mismatch_blocks_without_unlocking_recovery",
            ),
            "copilot": (
                "test_copilot_execute.DispatchAndReadinessTests.test_a_failed_dispatch_does_not_become_done_on_a_passing_check",
                "test_copilot_execute.DispatchAndReadinessTests.test_a_failed_dispatch_does_not_climb_the_escalation_ladder",
                "test_attempt_ledger.RalphDurableLoopTests.test_an_environment_failure_stops_the_loop_after_one_tick",
            ),
            "cursor": (
                "test_cursor_execute.FailureTests.test_a_dispatch_failure_is_classified_blocked_and_never_verified",
                "test_cursor_execute.FailureTests.test_a_logged_out_cli_is_named_and_recorded",
                "test_cursor_execute.IdentityRefusalTests",
            ),
            "stub": (
                "test_kit_scheduler.BatchTests.test_a_dispatch_failure_and_a_verify_failure_are_each_blocked_and_nothing_is_applied",
                "test_workflow_eval.DirectWorkflowTests.test_a_dispatch_failure_is_classified_and_not_graded_as_solved",
            ),
            "shared": (
                "test_attempt_ledger.ClassificationTests",
                "test_attempt_ledger.FailureClassAtTheDriverTests.test_a_logged_out_cli_is_classified_recorded_and_not_escalated",
                "test_proc_runner_wiring.DriverDispatchTests.test_a_missing_binary_comes_back_as_a_result_not_an_exception",
                "test_proc_runner_wiring.DriverDispatchTests.test_a_stalled_dispatch_is_bounded_rather_than_waited_on",
            ),
        },
    },
    {
        "id": "dependency-readiness",
        "title": "Dependency readiness",
        "steps": "18, 24",
        "claim": "an invalid graph refuses with zero dispatches and zero writes; one readiness rule; "
                 "a stale acceptance keeps its dependents out of the frontier",
        "capabilities": {},
        "tests": {
            "claude-code": (
                "test_claude_execute.DispatchAndReadinessTests.test_explicit_selection_obeys_the_same_dependency_rule_as_automatic",
                "test_claude_execute.DispatchAndReadinessTests.test_a_nonexistent_dependency_is_named",
                "test_claude_execute.DispatchAndReadinessTests.test_automatic_selection_explains_an_empty_frontier",
                "test_kit_graph.ZeroDispatchOnInvalidGraphTests",
            ),
            "codex": (
                "test_codex_execute_policy.ReadinessParityTests",
                "test_codex_execute_policy.DriverPolicyBoundaryTests.test_explicit_task_with_unfinished_dependency_is_ineligible",
                "test_kit_graph.ZeroDispatchOnInvalidGraphTests",
            ),
            "copilot": (
                "test_copilot_execute.DispatchAndReadinessTests.test_a_nonexistent_dependency_is_named",
                "test_copilot_execute.DispatchAndReadinessTests.test_an_unknown_task_id_is_named",
                "test_copilot_execute.DispatchAndReadinessTests.test_completed_work_is_not_silently_repeated",
                "test_kit_graph.ZeroDispatchOnInvalidGraphTests",
            ),
            "cursor": (
                "test_cursor_execute.ReadyTaskTests.test_a_ready_task_is_dispatched_once_verified_and_projected_done",
                "test_kit_graph.ZeroDispatchOnInvalidGraphTests",
                "test_kit_scheduler.DriverFreshnessTests.test_a_driver_refuses_a_task_whose_upstream_acceptance_is_stale",
            ),
            "stub": (
                "test_kit_scheduler.FreshnessTests",
            ),
            "shared": (
                "test_kit_graph.ValidateGraphTests",
                "test_kit_graph.ReadinessTests",
                "test_kit_graph.FrontierAndStateTests",
                "test_kit_contract.ReadinessTests",
            ),
        },
    },
    {
        "id": "verification-isolation",
        "title": "Verification isolation",
        "steps": "05",
        "claim": "verify commands run under bin/exec_policy.py; trusted-host is the sole opt-out "
                 "and reports itself; macOS Seatbelt is the only backend",
        "capabilities": {"claude-code": ("confined_verify",)},
        "tests": {
            "claude-code": (
                "test_proc_runner_wiring.DriverVerifyWiringTests",
            ),
            "codex": (
                "test_proc_runner_wiring.DriverVerifyWiringTests",
            ),
            "copilot": (
                "test_proc_runner_wiring.DriverVerifyWiringTests",
                "test_proc_runner_wiring.RalphVerifyTests.test_ralphs_verify_line_no_longer_runs_in_the_parent_shell",
            ),
            "cursor": (
                "test_proc_runner_wiring.DriverVerifyWiringTests",
            ),
            "stub": (
                "test_kit_scheduler.SecurityTests.test_a_worker_cannot_reach_the_main_tree_or_another_copy",
            ),
            "shared": (
                "test_exec_policy.EnforcementTests",
                "test_exec_policy.FailClosedTests.test_enforced_without_a_backend_refuses_rather_than_running",
                "test_exec_policy.FailClosedTests.test_trusted_host_is_reported_as_itself_not_as_enforcement",
                "test_exec_policy.VerifyRunnerTests",
                "test_exec_policy.BackendDetectionTests.test_darwin_reports_sandbox_exec",
                "test_proc_runner_wiring.ConfinedRunTests",
            ),
        },
    },
    {
        "id": "role-permissions",
        "title": "Role permissions",
        "steps": "06, 20",
        "claim": "review and verification dispatches carry the harness's documented restricted "
                 "form and extra flags cannot override it; a declared role a driver cannot run "
                 "is refused or disclosed",
        "capabilities": {"claude-code": ("tool_pin", "independent_review"),
                         "codex": ("sandbox_read_only", "independent_review"),
                         "copilot": ("tool_pin", "independent_review"),
                         "cursor": ("read_only_dispatch", "independent_review")},
        "tests": {
            "claude-code": (
                "test_claude_execute.RolePermissionTests",
            ),
            "codex": (
                "test_codex_execute.BuildDispatchTests.test_default_does_not_change_approval_mode_or_bypass_sandbox",
                "test_codex_execute.EndToEndRunHappyPathTests.test_review_with_stub_uses_supported_sandbox_without_mutating_kit",
                "test_codex_execute_policy.DriverPolicyBoundaryTests.test_extra_args_cannot_override_model_profile_or_model_config",
            ),
            "copilot": (
                "test_copilot_execute.ReviewPermissionTests",
            ),
            "cursor": (
                "test_cursor_adapter.DispatchArgvTests.test_read_only_dispatch_uses_mode_ask_and_never_force",
                "test_cursor_adapter.DispatchArgvTests.test_extra_args_that_would_override_the_recorded_choice_are_refused",
                "test_cursor_execute.ReviewTests.test_a_review_is_read_only_recorded_and_leaves_the_kit_alone",
                "test_cursor_execute.ReadyTaskTests.test_extra_args_that_would_change_the_recorded_choice_are_refused_before_probe",
            ),
            "stub": (
                "test_workflow_eval.AdapterTests.test_each_review_form_is_the_harness_documented_read_only_shape",
                "test_workflow_eval.AdapterTests.test_every_adapter_builds_a_dispatch_and_a_read_only_review_with_the_prompt_verbatim",
            ),
            "shared": (
                "test_role_contract.VocabularyTests.test_read_only_roles_hold_no_write_grant_and_write_roles_hold_exactly_theirs",
                "test_kit_contract.AdapterConformanceTests.test_an_unsupported_operation_raises_rather_than_returning_a_fake_answer",
                "test_repo_bench.JudgePermissionTests",
            ),
        },
    },
    {
        "id": "protected-state",
        "title": "Protected state",
        "steps": "05, 16, 24",
        "claim": "a worker's edit to its own task block is detected and recorded; the ledger and "
                 "every store live outside the tree; claims are O_EXCL; a worker's kit edit under "
                 "the scheduler is a recorded violation",
        "capabilities": {"claude-code": ("durable_attempts",), "codex": ("durable_attempts",),
                         "copilot": ("durable_attempts",), "cursor": ("durable_attempts",)},
        "tests": {
            "claude-code": (
                "test_attempt_ledger.ClaimAtTheDriverTests",
                "test_attempt_ledger.ProjectionFromFreshReadTests.test_a_worker_that_flipped_its_own_status_is_overwritten_and_reported",
            ),
            "codex": (
                "test_attempt_ledger.ClaimAtTheDriverTests",
                "test_attempt_ledger.ProjectionFromFreshReadTests.test_a_worker_that_flipped_its_own_status_is_overwritten_and_reported",
            ),
            "copilot": (
                "test_attempt_ledger.ClaimAtTheDriverTests",
                "test_attempt_ledger.ProjectionFromFreshReadTests.test_a_worker_that_flipped_its_own_status_is_overwritten_and_reported",
            ),
            "cursor": (
                "test_cursor_execute.ResumeTests.test_a_task_another_live_run_holds_is_refused",
                "test_attempt_ledger.ClaimAtTheDriverTests",
            ),
            "stub": (
                "test_kit_scheduler.SecurityTests",
                "test_kit_scheduler.RevisionTests.test_a_proposal_touching_acceptance_is_refused_whole",
                "test_workflow_eval.DirectWorkflowTests.test_touching_test_paths_is_recorded_as_tampering_and_never_buys_a_grade",
            ),
            "shared": (
                "test_kit_graph.PlanDriftTests",
                "test_attempt_ledger.ClaimTests",
                "test_attempt_ledger.StoreLocationTests",
            ),
        },
    },
    {
        "id": "verdict-provenance",
        "title": "Verdict provenance",
        "steps": "01, 09, 24",
        "claim": "acceptance depends on the typed verdict ledger and fails closed on an absent, "
                 "malformed, or conflicting verdict; completion is bound to current, "
                 "task-appropriate evidence",
        "capabilities": {},
        "tests": {
            "claude-code": (
                "test_claude_execute.EndToEndTautologicalVerifyTests",
                "test_claude_execute.EvidenceKindTests",
            ),
            "codex": (
                "test_codex_execute_policy.DriverPolicyBoundaryTests.test_absent_malformed_conflicting_and_interrupted_results_fail_closed",
                "test_codex_execute_policy.DriverPolicyBoundaryTests.test_acceptance_verdict_comes_only_from_a_correlated_terminal_message",
                "test_codex_execute_policy.DriverPolicyBoundaryTests.test_a_corrupt_ledger_line_degrades_to_unproven",
                "test_codex_execute_policy.DriverPolicyBoundaryTests.test_legacy_notes_are_readable_but_never_prove_success",
                "test_codex_execute_policy.DriverPolicyBoundaryTests.test_a_report_quoting_driver_fields_cannot_forge_a_review",
                "test_codex_execute_policy.DriverPolicyBoundaryTests.test_accept_without_a_machine_verdict_fails_closed_with_a_reason",
                "test_codex_execute_policy.DriverPolicyBoundaryTests.test_typed_record_rejects_non_integer_and_boolean_exit_codes",
                "test_codex_execute_policy.DriverPolicyBoundaryTests.test_later_review_supersedes_old_success_and_fingerprint_must_match",
            ),
            "copilot": (
                "test_copilot_execute.EndToEndPlanBudgetStopTests.test_budget_stop_is_not_recorded_when_the_task_already_has_a_verdict",
                "test_attempt_history.HistoryIsNeverCollapsedTests.test_a_budget_stop_never_supersedes_a_verdict_in_the_projection",
            ),
            "cursor": (
                "test_cursor_execute.BudgetStopTests.test_a_budget_stop_never_displaces_a_recorded_verdict",
            ),
            "stub": (
                "test_workflow_eval.ReviewedWorkflowTests",
                "test_kit_scheduler.ManifestTests.test_the_manifest_carries_artifacts_and_verdicts_but_no_transcript",
            ),
            "shared": (
                "test_kit_verify_hook.FreshnessTests",
                "test_kit_verify_hook.PrecheckTautologicalTests",
                "test_kit_graph.TransitionTests.test_project_status_refuses_a_verdict_with_no_dispatch_and_writes_nothing",
                "test_attempt_history.HistoryIsNeverCollapsedTests",
            ),
        },
    },
    {
        "id": "budget-admission",
        "title": "Budget admission",
        "steps": "08, 16",
        "claim": "every consuming operation is admitted before dispatch, refusals are recorded, a "
                 "dead attempt still counts, and a proxy figure never enters a priced total",
        "capabilities": {},
        "tests": {
            "claude-code": (
                "test_claude_execute.BudgetAdmissionTests",
                "test_claude_execute.ParsePlanBudgetTests",
                "test_claude_execute.EndToEndPlanBudgetStopTests",
            ),
            "codex": (
                "test_codex_execute.EndToEndPlanBudgetStopTests",
                "test_codex_execute.PlanBudgetExhaustedTests",
                "test_codex_execute.ParsePlanBudgetTests",
            ),
            "copilot": (
                "test_copilot_execute.BudgetAdmissionTests",
                "test_copilot_ralph.SpendAdmissionTests",
                "test_copilot_budget.BudgetLedgerTests.test_blocked_run_is_excluded_from_net_never_credited_a4",
                "test_copilot_budget.BudgetLedgerTests.test_not_counted_rows_skipped_from_every_total_t8",
            ),
            "cursor": (
                "test_cursor_execute.BudgetStopTests.test_a_reached_plan_budget_stops_before_the_probe_and_the_dispatch",
            ),
            "stub": (
                "test_kit_scheduler.AdmissionTests.test_one_admission_decision_covers_the_batch",
                "test_kit_scheduler.SecurityTests.test_a_worker_cannot_grant_itself_budget",
                "test_workflow_eval.CeilingAndCapTests",
                "test_workflow_eval.KitWorkflowTests.test_a_kit_whose_budget_is_spent_by_dead_attempts_refuses_and_records_the_budget_outcome",
            ),
            "shared": (
                "test_attempt_ledger.BudgetCarriesAcrossRunsTests.test_attempts_the_notes_file_never_saw_still_count_against_the_cap",
                "test_repo_bench.WouldExceedCeilingTests.test_missing_ceiling_is_a_refusal_not_a_permissive_default",
                "test_repo_bench.CostCeilingStopTests",
            ),
        },
    },
    {
        "id": "interruption-resume",
        "title": "Interruption and resume",
        "steps": "16",
        "claim": "a dead run's open attempt is closed as unknown, reconciled by re-running the "
                 "check, and never replayed; finished work is recognised without a dispatch",
        "capabilities": {"claude-code": ("durable_attempts",), "codex": ("durable_attempts",),
                         "copilot": ("durable_attempts",), "cursor": ("durable_attempts",)},
        "tests": {
            "claude-code": (
                "test_attempt_ledger.CrashAfterDispatchTests",
                "test_attempt_ledger.CrashBeforeProjectionTests.test_a_recorded_verdict_is_projected_not_re_earned",
            ),
            "codex": (
                "test_attempt_ledger.CrashAfterDispatchTests",
                "test_attempt_ledger.CrashBeforeProjectionTests.test_a_recorded_verdict_is_projected_not_re_earned",
            ),
            "copilot": (
                "test_attempt_ledger.CrashAfterDispatchTests",
                "test_attempt_ledger.CrashBeforeProjectionTests.test_a_recorded_verdict_is_projected_not_re_earned",
                "test_attempt_ledger.RalphDurableLoopTests.test_a_second_run_resumes_iteration_count_spend_and_history",
                "test_attempt_ledger.RalphDurableLoopTests.test_two_loops_on_one_goal_cannot_run_at_once",
            ),
            "cursor": (
                "test_cursor_execute.ResumeTests",
                "test_attempt_ledger.CrashAfterDispatchTests",
            ),
            "stub": (
                "test_kit_scheduler.ResumeTests",
                "test_workflow_eval.KitWorkflowTests.test_a_dead_attempt_is_settled_without_replay_and_the_resume_is_recorded",
                "test_workflow_eval.KitWorkflowTests.test_finished_work_left_by_a_dead_run_is_recognised_and_not_redispatched",
            ),
            "shared": (
                "test_attempt_ledger.RetryContextTests.test_context_is_bounded_names_unknown_attempts_and_the_trend",
                "test_kit_graph.ReadinessTests.test_naming_the_interrupted_task_resumes_it",
                "test_kit_graph.FrontierAndStateTests.test_interrupted_outranks_ready_because_nothing_here_schedules",
                "test_kit_graph.DiamondThroughTheDriverTests.test_a_dead_runs_task_is_resumed_by_name_and_never_walked_past",
            ),
        },
    },
    {
        "id": "filesystem-confinement",
        "title": "Filesystem confinement",
        "steps": "02, 10",
        "claim": "every write, read, or delete into a caller-selected root goes through "
                 "bin/safe_paths.py; benchmark patch, reference-test, and artifact escapes are "
                 "refused",
        "capabilities": {},
        "tests": {
            "cursor": (
                "test_cursor_adapter.InstallTests.test_a_destination_escaping_the_project_is_refused_not_written",
            ),
            "stub": (
                "test_kit_scheduler.SnapshotTests.test_a_snapshot_copies_files_keeps_modes_skips_links_and_excluded_dirs",
                "test_kit_scheduler.ConflictTests.test_a_file_the_user_changed_during_the_batch_is_never_overwritten",
            ),
            "shared": (
                "test_safe_paths.ContainmentTests",
                "test_safe_paths.RelativePathTests",
                "test_safe_paths.IdentifierTests",
                "test_kit_verify_hook.TaskIdConfinementTests",
                "test_repo_bench.SubstrateConfinementTests",
                "test_repo_bench.RunLoopSafetyTests.test_the_run_never_writes_the_real_store",
                "test_repo_bench.RunLoopSafetyTests.test_target_repo_is_byte_identical_after_a_full_run",
                "test_repo_bench.OracleTestsTests.test_blob_lands_in_the_substrate_and_never_in_the_candidate_sandbox",
            ),
        },
    },
    {
        "id": "installation-ownership",
        "title": "Installation ownership",
        "steps": "11, 23",
        "claim": "an installer classifies every destination, never overwrites what it does not "
                 "own, restates the precondition when it writes, rolls back only its own bytes, "
                 "and fails a stale plan safe",
        "capabilities": {"cursor": ("skill_files", "subagent_files")},
        "tests": {
            "claude-code": (
                "test_harness_select.ClaudeCodeInstallCliTests.test_claude_code_install_writes_nothing_and_prints_marketplace_message",
            ),
            "codex": (
                "test_install_ownership.CodexStalePlanTests",
            ),
            "copilot": (
                "test_install_ownership.CopilotFirstInstallTests",
                "test_install_ownership.CopilotReinstallAndUpgradeTests",
                "test_install_ownership.CopilotPreservationTests",
                "test_install_ownership.CopilotRollbackTests",
                "test_install_ownership.CopilotSymlinkTests",
                "test_install_ownership.CopilotAdoptionTests",
            ),
            "cursor": (
                "test_cursor_adapter.InstallTests",
            ),
            "shared": (
                "test_harness_select.DetectTests",
                "test_harness_select.InstallCopilotDryRunTests",
                "test_harness_select.InstallCopilotIdempotenceTests",
                "test_install_ownership.SafeCreateTests",
            ),
        },
    },
    {
        "id": "privacy-eligibility",
        "title": "Privacy eligibility",
        "steps": "13, 22",
        "claim": "free text is redacted and bounded before it is persisted or dispatched and "
                 "reported by kind and count; recall is eligibility-gated and budgeted; the digest "
                 "carries metadata only; harness homes are read-only",
        "capabilities": {},
        "tests": {
            "stub": (
                "test_workflow_eval.DirectWorkflowTests.test_a_credential_in_the_statement_is_redacted_before_dispatch_and_counted_by_kind",
                "test_workflow_eval.PlanTests.test_a_statement_with_a_credential_shape_is_labelled_and_never_quoted",
                "test_workflow_eval.DirectWorkflowTests.test_the_prompt_is_leak_free_and_the_store_is_written_only_after_every_dispatch",
            ),
            "shared": (
                "test_privacy_primitives.RedactionTests",
                "test_privacy_primitives.DataHomeTests",
                "test_privacy_primitives.ResolutionTests",
                "test_privacy_primitives.PrivateCreationTests",
                "test_privacy_primitives.RetentionTests",
                "test_privacy_layout.PrivacyLayoutTests",
                "test_memory_recall.GateTests",
                "test_memory_recall.BudgetTests",
                "test_memory_recall.ProvenanceAndScopeTests",
                "test_lessons_store.RecallTests",
                "test_lessons_store.CompatibilityTests.test_the_module_dispatches_nothing_and_reads_no_home",
                "test_attempt_ledger.LedgerRecordTests.test_verify_tails_are_redacted_before_they_are_stored",
                "test_journal_collect.ContentHygieneTests.test_transcript_text_marker_never_reaches_the_written_digest",
                "test_journal_summarize.IsolatedSummaryDispatchTests",
                "test_journal_collect.ReadOnlyProofTests.test_source_and_kit_trees_are_byte_identical_only_journal_dir_gains_files",
                "test_journal_sources.ReadOnlyProofTests.test_combined_fixture_tree_is_byte_identical_after_run_adapters",
                "test_copilot_usage.ReadOnlyProofTests.test_fixture_home_bytes_unchanged_and_no_new_files",
                "test_codex_usage.ReadOnlyProofTests.test_temp_home_file_tree_byte_identical_after_run",
                "test_kit_verify_hook.StaticSafetyTests.test_module_never_calls_path_home",
            ),
        },
    },
)

#: Tests that prove a kit written before the contract existed still parses, schedules, and
#: scores: no `depends:`, no ledger, no artifact versions.
LEGACY_TESTS = (
    "test_kit_graph.LegacyKitsTests.test_every_kit_parses_and_every_unfinished_kit_is_valid",
    "test_role_contract.GrammarTests.test_every_legacy_kit_parses_and_the_two_with_roles_resolve_as_extended",
    "test_kit_scheduler.FreshnessTests.test_a_legacy_acceptance_is_unknown_not_stale_and_status_says_nothing_alarming",
    "test_codex_execute_policy.DriverPolicyBoundaryTests.test_legacy_notes_are_readable_but_never_prove_success",
    "test_lessons_store.RecallTests.test_a_legacy_entry_is_a_candidate_never_a_rule",
    "test_copilot_execute.PrefsAwareLadderTests.test_prefs_none_identical_to_legacy",
    "test_kit_contract.LedgerFieldTests",
    "test_attempt_history.UnknownStaysUnknownTests.test_a_notes_line_takes_its_harness_from_the_ledger_run_it_projects",
    "test_harness_select.InstallCopilotAgentsOnlyBackwardCompatTests.test_agents_only_bundle_with_no_skills_dir_installs_cleanly",
    "test_routing_scorecard.BudgetStopKeyOptionalityTests.test_field_less_legacy_kit_quality_has_no_budget_stop_key",
    "test_role_ledger.MarginalTests.test_legacy_line_no_marginal_key_parses_with_marginal_none",
)

#: Tests that prove no real client is ever spawned by the suite, a verify command, or a demo.
NO_REAL_CLI_TESTS = (
    "test_proc_runner_wiring.OneRunnerTests",
    "test_claude_execute.DryRunSpawnsNothingTests",
    "test_claude_execute.ReviewDryRunTests.test_review_dry_run_prints_dispatch_and_spawns_nothing",
    "test_codex_execute.DryRunSpawnsNothingTests.test_dry_run_never_touches_subprocess_and_leaves_kit_untouched",
    "test_copilot_execute.DryRunSpawnsNothingTests.test_dry_run_never_touches_subprocess_and_leaves_tasks_file_untouched",
    "test_copilot_ralph.CliSafetySmokeTests.test_demo_and_dry_run_spawn_nothing",
    "test_copilot_budget.BudgetLedgerTests.test_budget_command_never_dispatches_writes_or_loads_pricing_or_prefs",
    "test_cursor_execute.DryRunTests.test_dry_run_prints_the_argv_and_spawns_nothing_not_even_the_probe",
    "test_cursor_execute.ReviewTests.test_a_review_dry_run_spawns_nothing",
    "test_cursor_execute.SourceHygieneTests.test_help_runs_offline",
    "test_cursor_adapter.RegistryAndPricingTests.test_the_demo_and_help_run_offline",
    "test_cursor_adapter.RegistryAndPricingTests.test_the_adapter_carries_no_process_primitive_of_its_own",
    "test_cursor_adapter.InstallTests.test_doctor_reports_without_spawning_anything_but_the_named_stub",
    "test_kit_scheduler.DryRunAndCliTests.test_dry_run_claims_nothing_copies_nothing_spawns_nothing",
    "test_kit_scheduler.DryRunAndCliTests.test_the_demo_runs_offline",
    "test_kit_scheduler.DryRunAndCliTests.test_the_module_carries_no_shell_strings_and_no_bare_subprocess",
    "test_workflow_eval.CliTests.test_demo_runs_offline_and_spends_nothing",
    "test_workflow_eval.AdapterTests.test_the_module_names_no_model_id_and_carries_no_process_primitive",
    "test_attempt_ledger.RalphDurableLoopTests.test_demo_and_dry_run_still_spawn_nothing",
    "test_plugin_staleness.SourceHygieneTests.test_no_real_cli_invocation_outside_comments",
    "test_telemetry_snapshot.SourceLawTests.test_no_process_spawning_tokens_anywhere_in_the_source",
    "test_repo_bench.RunLoopSafetyTests.test_every_cell_was_dispatched_through_the_injected_stub",
    "test_release_gate.ModuleShapeTests.test_module_carries_no_process_primitive_or_home_path",
    "test_graph_ground.SourceHygieneTests.test_the_module_never_invokes_graphify_or_spawns_on_its_own",
    "test_graph_brief.SourceIntrospectionTests.test_no_home_dir_or_network_or_subprocess_primitives_in_any_function",
    "test_lessons_promote.NoDispatchImportTests.test_source_has_no_subprocess_or_execute_module_imports",
    "test_journal_schedule.ModuleSafetyTests.test_module_has_no_subprocess",
    "test_routing_policy.DriverCommandLineTests.test_dry_run_under_each_policy_previews_the_decision_and_spawns_nothing",
)

# ---- the release checklist, migration notes, triggers, and prepared commands ------------------

#: Guarantee -> where its evidence is -> what remains unresolved. Text, because these are
#: statements about the repository; every command they name is resolved by `check`.
CHECKLIST = (
    {
        "guarantee": "The full suite is green on this tree",
        "evidence": "`python3 -m unittest discover -s tests` from the repo root, exit 0; the count "
                    "is quoted only in the commit that changed it",
        "limit": "a green suite says the units work; it does not say a vendor client was run",
    },
    {
        "guarantee": "Every advertised harness passes the eleven shared contracts through a stub",
        "evidence": "`python3 bin/release_gate.py contracts --run`: every mapped test id resolves "
                    "and passes; the table below names them per harness",
        "limit": "stub conformance only; the installed-client column is the registry's, and it "
                 "reads `unknown` for every real harness capability nobody has run",
    },
    {
        "guarantee": "Unknown host capabilities stay visible",
        "evidence": "`python3 bin/harness_adapter.py` prints every row with its three states; "
                    "`harness_adapter.requires` treats `unknown` as no",
        "limit": "a row becomes `supported` only when someone runs the client, records the date "
                 "and the client version in the row, and commits that edit by hand",
    },
    {
        "guarantee": "Both generated documentation mirrors and the Codex prompt mirrors are current",
        "evidence": "`python3 bin/docs_build.py check`, `python3 bin/copilot_docs.py check`, "
                    "`python3 bin/sync_codex_surfaces.py check`, `python3 bin/sync_pricing_refs.py "
                    "--check`, and this gate's `check` (the marked block of docs/RELEASE.md), all "
                    "exit 0",
        "limit": "`mkdocs build --strict` runs only in CI; the lock targets Linux",
    },
    {
        "guarantee": "Private runtime stores cannot be committed and default outside the tree",
        "evidence": "`python3 bin/release_gate.py packaging` finds no store without a root-anchored "
                    "ignore rule and no tracked file under one; `tests/test_privacy_layout.py` "
                    "pins the same for every `runtime_data.STORES` name",
        "limit": "a plugin install copies the whole directory and ignores `.gitignore`; a legacy "
                 "in-tree store is copied with it -- the prune runbook in docs/PRIVACY.md is "
                 "manual by design",
    },
    {
        "guarantee": "Packaging manifests agree and the build supply chain is pinned",
        "evidence": "`packaging`: the Claude plugin manifest and its marketplace agree on name and "
                    "description, every GitHub Action is pinned to a full commit SHA, deploy "
                    "credentials exist only in the deploy job, every site package carries a sha256",
        "limit": "the Codex package carries its own version line and is bumped by hand beside the "
                 "plugin version",
    },
    {
        "guarantee": "No-clobber upgrades and legacy kits keep working",
        "evidence": "the installation-ownership contract row, plus the legacy-kit tests named below",
        "limit": "an install made before the ownership manifest existed classifies as unmanaged "
                 "when it differs; `--adopt-existing` is the one-run remedy and keeps a backup",
    },
    {
        "guarantee": "Pricing is one file per harness and no generated mirror has drifted",
        "evidence": "the `data` section of `python3 bin/harness_update.py check` reports "
                    "up-to-date with zero stale mirrors and every docs label ok (read-only; it "
                    "also ages each `cached_date`)",
        "limit": "the card's exit code also covers the user's installed Claude and Copilot homes, "
                 "which drift from an unmerged branch by design; prices are labelled snapshots and "
                 "their age is reported, never corrected here",
    },
    {
        "guarantee": "Routing defaults changed only by a reviewed, versioned proposal",
        "evidence": "`python3 bin/workflow_eval.py policy` lists the version in force and its "
                    "journal; no driver reads the file (a test fails if one starts to)",
        "limit": "no live evaluation has run, so no proposal has evidence behind it yet",
    },
    {
        "guarantee": "Nothing here ran a paid call, wrote a home directory, or pushed",
        "evidence": "the invariants in CLAUDE.md, the no-real-CLI tests named below, and this "
                    "gate's own process list (read-only git, in-process unittest)",
        "limit": "the optional live commands below are prepared and stay unrun until a person "
                 "runs them on their own account",
    },
)

#: Surface -> how to move forward -> how to move back. Every command is resolved by `check`.
MIGRATION_NOTES = (
    {
        "surface": "Runtime stores (memory, telemetry, journal, benchruns, prefs, trends, "
                   "attempts, evals)",
        "forward": "`python3 bin/runtime_data.py where`; an in-tree store keeps being used; "
                   "`python3 bin/runtime_data.py migrate --store NAME --apply` copies it out and "
                   "never deletes the original",
        "back": "delete the copy; the original was never touched. `export` copies anywhere; "
                "`forget` lists before it deletes and deletes only with `--apply`",
    },
    {
        "surface": "Copilot home (`~/.copilot`)",
        "forward": "`python3 bin/harness_select.py install --harness copilot` (add "
                   "`--adopt-existing` once for files installed before the ownership manifest)",
        "back": "each adopted file keeps a `.polytropos-bak` beside it; a run that fails midway "
                "rolls back only the bytes it wrote",
    },
    {
        "surface": "Codex home (`~/.codex`)",
        "forward": "`python3 bin/harness_select.py install --harness codex`; "
                   "`python3 bin/harness_select.py doctor --harness codex` diagnoses; "
                   "`python3 bin/harness_update.py apply --only codex` refreshes managed copies",
        "back": "`python3 bin/harness_select.py restore-legacy --harness codex` restores proven "
                "legacy copies from the backup root `retire-legacy` wrote; `config.toml` is never "
                "written, so nothing there needs undoing",
    },
    {
        "surface": "Cursor project bundle (`.cursor/`)",
        "forward": "`python3 bin/harness_select.py install --harness cursor --project DIR`; "
                   "`python3 bin/harness_select.py doctor --harness cursor --project DIR`",
        "back": "the manifest at `.cursor/polytropos/install-manifest.json` names every file the "
                "installer owns; remove those and only those",
    },
    {
        "surface": "Claude Code plugin cache",
        "forward": "bump `.claude-plugin/plugin.json`, then `claude plugin update "
                   "polytropos@polytropos-local`, then the prune runbook in docs/PRIVACY.md",
        "back": "`claude plugin install` of the previous version directory; repo code never "
                "touches `~/.claude`",
    },
    {
        # Named by its owner's constant, not its file name: tests/test_workflow_eval.py pins
        # that no module but workflow_eval mentions the applied policy file, and this gate does
        # not read it either.
        "surface": "Routing policy (`workflow_eval.POLICY_FILE` under the `prefs` store)",
        "forward": "`python3 bin/workflow_eval.py propose` -> `review` -> `apply`; every version kept",
        "back": "`python3 bin/workflow_eval.py rollback --version N`; the replaced version is kept too",
    },
    {
        "surface": "Kits written before the contract",
        "forward": "nothing to do: a kit without `depends:` is a chain, without a ledger its "
                   "freshness is `unknown` and disclosed, and `python3 bin/kit_contract.py graph "
                   "--kit DIR` names anything the validator refuses",
        "back": "not applicable; no kit file is rewritten by a driver",
    },
    {
        "surface": "Generated mirrors (docs-site/, copilot-docs/, codex/prompts/, the "
                   "pricing references, the block in docs/RELEASE.md)",
        "forward": "edit the source, then `python3 bin/docs_build.py build`, `python3 "
                   "bin/copilot_docs.py build`, `python3 bin/sync_codex_surfaces.py build`, "
                   "`python3 bin/sync_pricing_refs.py`, `python3 bin/release_gate.py build`",
        "back": "`git checkout -- <mirror>`; the mirrors carry no state of their own",
    },
)

#: What a new harness or model release triggers. Targeted, never automatic: nothing below
#: edits a registry row or a routing default.
REEVALUATION_TRIGGERS = (
    {
        "trigger": "A vendor ships a new client version",
        "do": "`python3 bin/release_gate.py reverify --harness NAME --released YYYY-MM-DD` lists "
              "every row whose verification predates the release; run the driver's `--dry-run`, "
              "then the documented smoke on your own account; record `verified_on` and "
              "`client_version` in the row by hand",
        "never": "a row is never re-dated without a run, and a failing smoke sets `verified` "
                 "to `unsupported` with the date rather than deleting the row",
    },
    {
        "trigger": "A vendor ships or retires a model",
        "do": "edit that harness's pricing file only (`cached_date` too); `python3 "
              "bin/sync_pricing_refs.py`; `python3 bin/harness_update.py check`; "
              "`python3 bin/model_registry.py` must resolve the new id to one tier",
        "never": "no price, ratio, or model id is written anywhere but the pricing file",
    },
    {
        "trigger": "A routing default looks wrong for a model",
        "do": "`python3 bin/workflow_eval.py plan` on a held-out repository, then `run --live "
              "--max-usd N --max-dispatches N` on your own account, then `propose` -> `review` -> "
              "`apply`",
        "never": "a default is never promoted from a single repeat, from tasks that already backed "
                 "the policy, or without a named review",
    },
    {
        "trigger": "A repeated failure on one harness",
        "do": "`python3 bin/lessons_store.py observe` an observation with provenance and scope; "
              "`promote` only on recurrence across distinct sources or by explicit ask",
        "never": "no permanent instruction is added after a single failure",
    },
    {
        "trigger": "The plugin version is bumped",
        "do": "`python3 bin/release_gate.py check`, both doc generators' `check`, the full "
              "suite, then the prune runbook in docs/PRIVACY.md after `claude plugin update`",
        "never": "a bump never rewrites a `verified_on` date",
    },
)

#: Bounded live commands, prepared here and never run by this repository. Each spends or
#: contacts a vendor with the user's own credentials.
PREPARED_COMMANDS = (
    {
        "name": "Cursor identity and read-only smoke",
        "command": "python3 bin/harness_select.py doctor --harness cursor --project DIR  # prints "
                   "the smoke; never runs it",
        "then": "agent -p --trust --workspace DIR --output-format json --mode ask "
                "\"Reply with the single word ready\"",
        "records": "cursor `identity_probe`, `dispatch`, `read_only_dispatch` rows",
    },
    {
        "name": "Each driver's argv, spawning nothing",
        "command": "python3 bin/claude_execute.py run --kit DIR --dry-run; python3 "
                   "bin/codex_execute.py run --kit DIR --dry-run; python3 bin/copilot_execute.py "
                   "run --kit DIR --dry-run; python3 bin/cursor_execute.py run --kit DIR --dry-run",
        "then": "one authorised live `run` on a kit you own, on your own account",
        "records": "that harness's `dispatch` and `durable_attempts` rows",
    },
    {
        "name": "The bounded workflow evaluation",
        "command": "python3 bin/workflow_eval.py plan --repo DIR --harness claude --models "
                   "sonnet,haiku --workflows direct,reviewed,kit --repeats 2 --limit 6 --test-cmd "
                   "\"python -m pytest -q\"",
        "then": "the same flags with `run --live --max-usd 5 --max-dispatches 60`",
        "records": "that harness's `workflow_evaluation` and `independent_review` rows; the "
                   "run's card is the evidence a proposal cites",
    },
    {
        "name": "The bounded benchmark",
        "command": "python3 bin/repo_bench.py plan --repo DIR --models sonnet,haiku",
        "then": "`run --live --max-usd N` with the printed plan",
        "records": "nothing in the registry; the run's verdicts feed `repo_bench apply`",
    },
)

#: Top-level tracked paths and the role each plays in the package. An unlisted path is a
#: finding: either it belongs in a role here or it does not belong in the tree.
TREE_ROLES = {
    ".agents": "Codex marketplace manifest (packaging)",
    ".claude": "this repository's own kits and agents: development history, not installed by the plugin",
    ".claude-plugin": "Claude Code plugin manifest and local marketplace (packaging)",
    ".codex-plugin": "Codex plugin manifest (packaging)",
    ".github": "the docs-site CI workflow",
    ".gitignore": "packaging: root-anchored rules for every private store",
    "CLAUDE.md": "executor guardrails, loaded into every session",
    "HANDOFF.md": "work record for the next session",
    "LICENSE": "packaging",
    "README.md": "documentation source",
    "SECURITY.md": "documentation source: what is and is not a boundary",
    "SETUP.md": "documentation source",
    "bin": "engines, stdlib-only",
    "codex": "Codex bundle (codex/prompts/ is a generated mirror)",
    "copilot": "Copilot bundle",
    "copilot-docs": "generated mirror (bin/copilot_docs.py)",
    "cursor": "Cursor bundle",
    "data": "pricing files, one per harness: the numeric source of truth",
    "docs": "documentation source (docs/RELEASE.md carries this gate's generated block)",
    "docs-site": "generated mirror (bin/docs_build.py)",
    "docs-src": "documentation fragments and the hash-locked site toolchain",
    "mkdocs.yml": "site configuration",
    "primitives": "capability registry, historical primitive matrix, primitive model",
    "skills": "plugin skills: runtime behaviour",
    "tasks": "legacy kit ledgers and the lessons file, committed by design",
    "tests": "the suite",
}

#: Tracked paths that must never appear, whatever the top-level role.
FORBIDDEN_TRACKED = (
    ("__pycache__/", "bytecode cache"),
    (".pyc", "bytecode"),
    (".DS_Store", "Finder metadata"),
    ("site-build/", "mkdocs build output"),
    (".claude/settings.local.json", "local settings"),
    ("/verify-pass/", "verify-pass markers"),
    ("graphify-out/", "graph output"),
    ("value-report", "generated value report"),
    ("conv-summaries/", "conversation summaries"),
)


# ---- helpers ----------------------------------------------------------------------------------

def _load_sibling(name):
    """Load `bin/<name>.py` by path -- `bin/` is not a package. Never monkeypatches."""
    spec = importlib.util.spec_from_file_location(f"_release_gate_{name}", BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_SIBLINGS = {}


def _sibling(name):
    if name not in _SIBLINGS:
        _SIBLINGS[name] = _load_sibling(name)
    return _SIBLINGS[name]


def _read_json(path):
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def git_read(repo_root, verb, *args):
    """A read-only git verb through the process runner -> (rc, stdout). Refuses any other."""
    if verb not in GIT_READ_VERBS:
        raise ValueError(f"release_gate runs only {GIT_READ_VERBS}; refused git {verb!r}")
    pr = _sibling("proc_runner")
    result = pr.run(["git", verb, *args], cwd=str(repo_root), timeout=60, name=f"git {verb}")
    return result.get("rc"), result.get("stdout") or ""


def revision(repo_root=REPO_ROOT):
    """The tree this gate is looking at: sha, commit date, and the dirty count. Live output
    only -- never part of the generated block."""
    rc, sha = git_read(repo_root, "rev-parse", "HEAD")
    if rc != 0:
        return {"sha": None, "committed_on": None, "dirty": None, "note": "not a git checkout"}
    _, when = git_read(repo_root, "log", "-1", "--format=%cI")
    rc_s, status = git_read(repo_root, "status", "--porcelain")
    dirty = len([ln for ln in status.splitlines() if ln.strip()]) if rc_s == 0 else None
    return {"sha": sha.strip(), "committed_on": when.strip()[:10] or None, "dirty": dirty,
            "note": ""}


def tracked_paths(repo_root=REPO_ROOT):
    """Every tracked path, or None when git cannot answer."""
    rc, out = git_read(repo_root, "ls-files", "-z")
    if rc != 0:
        return None
    return [p for p in out.split("\0") if p]


def _parser_default(parser, flag):
    """The default of `flag` anywhere in an argparse tree, or None."""
    for action in parser._actions:
        if flag in getattr(action, "option_strings", ()):
            return action.default
        choices = getattr(action, "choices", None)
        if isinstance(choices, dict):
            for sub in choices.values():
                if isinstance(sub, argparse.ArgumentParser):
                    found = _parser_default(sub, flag)
                    if found is not None:
                        return found
    return None


def binary_name(harness):
    """The client binary a driver dispatches to, read from the driver's own parser."""
    module = DRIVER_MODULES.get(harness)
    flag = HARNESS_FACTS[harness]["binary_flag"]
    if not module or not flag:
        return None
    mod = _sibling(module)
    build = getattr(mod, "build_parser", None)
    if build is None:
        return None
    return _parser_default(build(), flag)


# ---- versions ----------------------------------------------------------------------------------

def contract_versions():
    """Every contract version constant, read from its owner. Deterministic."""
    rows = []
    for label, module, attr in VERSION_SOURCES:
        value = getattr(_sibling(module), attr, None)
        rows.append({"contract": label, "owner": f"bin/{module}.py", "version": value})
    rows.append({"contract": "release gate", "owner": "bin/release_gate.py", "version": GATE_VERSION})
    return rows


_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_TOOLCHAIN = re.compile(r"^(mkdocs(?:-material)?)==([0-9][0-9A-Za-z.]*)", re.M)
_FLOOR = re.compile(r"\b(3\.\d+)\+")


def package_versions(repo_root=REPO_ROOT):
    """Manifest, registry, matrix, pricing, and toolchain versions. Deterministic."""
    root = Path(repo_root)
    plugin = _read_json(root / ".claude-plugin" / "plugin.json") or {}
    marketplace = _read_json(root / ".claude-plugin" / "marketplace.json") or {}
    codex_plugin = _read_json(root / ".codex-plugin" / "plugin.json") or {}
    codex_market = _read_json(root / ".agents" / "plugins" / "marketplace.json") or {}
    registry = _read_json(root / "primitives" / "harness-capabilities.json") or {}
    matrix = _read_json(root / "primitives" / "harness-matrix.json") or {}
    model = _read_json(root / "primitives" / "model.json") or {}
    try:
        requirements = (root / "docs-src" / "requirements.txt").read_text(encoding="utf-8")
    except OSError:
        requirements = ""
    try:
        setup = (root / "SETUP.md").read_text(encoding="utf-8")
    except OSError:
        setup = ""
    floor = _FLOOR.search(setup)
    pricing = {}
    for harness, rel in PRICING_FILES.items():
        payload = _read_json(root / rel) or {}
        models = payload.get("models")
        pricing[harness] = {
            "file": rel,
            "cached_date": payload.get("cached_date"),
            "models": len(models) if isinstance(models, (dict, list)) else 0,
        }
    return {
        "plugin": {"name": plugin.get("name"), "version": plugin.get("version"),
                   "description": plugin.get("description")},
        "marketplace": {
            "name": marketplace.get("name"),
            "plugins": [{"name": p.get("name"), "description": p.get("description")}
                        for p in marketplace.get("plugins", []) if isinstance(p, dict)],
        },
        "codex_plugin": {"name": codex_plugin.get("name"), "version": codex_plugin.get("version")},
        "codex_marketplace": {
            "name": codex_market.get("name"),
            "plugins": [p.get("name") for p in codex_market.get("plugins", []) if isinstance(p, dict)],
        },
        "registry_schema": registry.get("schema"),
        "matrix_schema": matrix.get("schema"),
        "matrix_pin": (matrix.get("source") or {}).get("aesop_commit"),
        "matrix_verified": (matrix.get("source") or {}).get("verified"),
        "primitive_model_schema": model.get("schema"),
        "pricing": pricing,
        "toolchain": {name: ver for name, ver in _TOOLCHAIN.findall(requirements)},
        "python_floor": floor.group(1) if floor else None,
    }


# ---- the operational matrix --------------------------------------------------------------------

def _registry(repo_root=REPO_ROOT):
    ha = _sibling("harness_adapter")
    return ha, ha.load_capabilities(Path(repo_root) / "primitives" / "harness-capabilities.json")


def harness_matrix(repo_root=REPO_ROOT, with_binaries=True):
    """Per harness: what the registry says, what the drivers say, what the pricing file says.
    Deterministic when `with_binaries` is True too (binaries are parser defaults)."""
    ha, registry = _registry(repo_root)
    kc = _sibling("kit_contract")
    versions = package_versions(repo_root)
    out = {}
    for harness in HARNESSES:
        facts = HARNESS_FACTS[harness]
        entry = registry["harnesses"].get(harness) or {}
        rows = []
        for name, raw in sorted((entry.get("capabilities") or {}).items()):
            row = ha.capability(
                name,
                product=raw.get("product", ha.UNKNOWN),
                implemented=raw.get("implemented", ha.UNKNOWN),
                verified=raw.get("verified", ha.UNKNOWN),
                source=raw.get("source", ""),
                verified_on=raw.get("verified_on"),
                note=raw.get("note", ""),
            )
            row["client_version"] = raw.get("client_version")
            row["effective"] = ha.effective(row)
            rows.append(row)
        dates = sorted(r["verified_on"] for r in rows if r["verified_on"])
        client_versions = sorted({r["client_version"] for r in rows if r.get("client_version")})
        pricing = versions["pricing"].get(harness) or {"file": None, "cached_date": None, "models": 0}
        role_support = {role: state for role, (state, _why) in
                        (kc.ROLE_SUPPORT.get(harness) or {}).items()}
        out[harness] = {
            "label": facts["label"],
            "driver": facts["driver"],
            "binary": binary_name(harness) if with_binaries else None,
            "binary_flag": facts["binary_flag"],
            "client_mode": entry.get("client_mode", "unknown"),
            "client_version": ", ".join(client_versions) if client_versions else "not recorded",
            "pricing_file": entry.get("pricing_file") or pricing["file"],
            "pricing_cached_date": pricing["cached_date"],
            "roster_models": pricing["models"],
            "bundle": facts["bundle"],
            "install": facts["install"],
            "review_form": facts["review_form"],
            "eval_adapter": facts["eval_adapter"],
            "role_support": role_support,
            "capabilities": rows,
            "verified_supported": [r["name"] for r in rows if r["verified"] == ha.SUPPORTED],
            "unknown": [r["name"] for r in rows if r["effective"] == ha.UNKNOWN],
            "unsupported": [r["name"] for r in rows if r["effective"] == ha.UNSUPPORTED],
            "latest_evidence": dates[-1] if dates else None,
            "in_registry": bool(entry),
        }
    return out


def historical_matrix(repo_root=REPO_ROOT):
    """aesop's product-support matrix, summarised and left exactly as pinned."""
    payload = _read_json(Path(repo_root) / "primitives" / "harness-matrix.json") or {}
    source = payload.get("source") or {}
    rows = []
    for harness, entry in sorted((payload.get("harnesses") or {}).items()):
        cells = entry.get("cells") or {}
        native = sorted(k for k, v in cells.items() if v.get("support") == "native")
        fallback = sorted(k for k, v in cells.items() if v.get("support") == "fallback")
        rows.append({"harness": harness, "goal_mode": entry.get("goal_mode"),
                     "native": native, "fallback": fallback})
    return {"schema": payload.get("schema"), "pin": source.get("aesop_commit"),
            "verified": source.get("verified"), "rows": rows}


# ---- contracts: stub conformance beside installed-client verification -------------------------

@contextmanager
def _tests_on_path(tests_dir):
    tests_dir = str(tests_dir)
    added = tests_dir not in sys.path
    if added:
        sys.path.insert(0, tests_dir)
    try:
        yield
    finally:
        if added and tests_dir in sys.path:
            sys.path.remove(tests_dir)


def _iter_tests(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _iter_tests(item)
        else:
            yield item


def resolve_test_ids(ids, tests_dir=TESTS_DIR):
    """`{id: count}` for ids that name at least one real test, `{id: 0}` for those that do not.
    A loader failure is a zero, not an exception: the point is to report every rotten id."""
    loader = unittest.TestLoader()
    out = {}
    with _tests_on_path(tests_dir):
        for tid in ids:
            try:
                suite = loader.loadTestsFromName(tid)
            except Exception:  # noqa: BLE001 -- any loader failure means unresolved
                out[tid] = 0
                continue
            cases = [t for t in _iter_tests(suite) if type(t).__name__ != "_FailedTest"]
            failed = [t for t in _iter_tests(suite) if type(t).__name__ == "_FailedTest"]
            out[tid] = 0 if failed or not cases else len(cases)
    return out


def run_test_ids(ids, tests_dir=TESTS_DIR):
    """Run the named tests in-process, quietly -> counts. This is the repository's own suite
    through its own loader; it spawns nothing this module chose."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    with _tests_on_path(tests_dir):
        for tid in ids:
            suite.addTests(loader.loadTestsFromName(tid))
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream, verbosity=0).run(suite)
    return {
        "ran": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "ok": result.wasSuccessful(),
        "detail": "" if result.wasSuccessful() else stream.getvalue()[-4000:],
    }


def _installed_verdict(rows_by_name, names, ha):
    """The registry's answer for the host side of one contract cell."""
    if not names:
        return {"verdict": "polytropos's own", "rows": [],
                "note": "no host capability backs this contract; stub conformance is the evidence"}
    rows = []
    for name in names:
        row = rows_by_name.get(name)
        if row is None:
            rows.append({"name": name, "verified": "missing", "verified_on": None})
        else:
            rows.append({"name": name, "verified": row["verified"], "verified_on": row["verified_on"],
                         "client_version": row.get("client_version")})
    states = {r["verified"] for r in rows}
    if "missing" in states:
        verdict = "missing row"
    elif states == {ha.SUPPORTED}:
        verdict = "verified " + ", ".join(sorted({r["verified_on"] for r in rows if r["verified_on"]}))
    elif ha.UNSUPPORTED in states:
        verdict = "unsupported"
    else:
        verdict = "unknown"
    return {"verdict": verdict, "rows": rows, "note": ""}


def contracts_report(repo_root=REPO_ROOT, run=False, resolver=None, runner=None,
                     harnesses=HARNESSES):
    """The evidence table: per contract, per harness, the stub-conformance tests (resolved,
    optionally run) beside the registry's installed-client verdict."""
    ha, _ = _registry(repo_root)
    matrix = harness_matrix(repo_root, with_binaries=False)
    resolver = resolver or resolve_test_ids
    runner = runner or run_test_ids
    report = {"schema": GATE_VERSION, "run": run, "contracts": []}
    all_ids = []
    for contract in CONTRACTS:
        cells = {}
        for harness in tuple(harnesses) + (SHARED,):
            ids = tuple(contract["tests"].get(harness, ()))
            all_ids.extend(ids)
            rows_by_name = {r["name"]: r for r in matrix.get(harness, {}).get("capabilities", [])}
            resolved = resolver(ids) if ids else {}
            cell = {
                "tests": list(ids),
                "resolved": resolved,
                "unresolved": [tid for tid, n in resolved.items() if not n],
                "test_count": sum(resolved.values()),
                "run": None,
                "installed_client": (_installed_verdict(rows_by_name, contract["capabilities"].get(harness, ()), ha)
                                     if harness != SHARED else None),
            }
            if run and ids:
                cell["run"] = runner(ids)
            cells[harness] = cell
        report["contracts"].append({
            "id": contract["id"], "title": contract["title"], "steps": contract["steps"],
            "claim": contract["claim"], "cells": cells,
        })
    legacy = resolver(LEGACY_TESTS) if LEGACY_TESTS else {}
    no_cli = resolver(NO_REAL_CLI_TESTS) if NO_REAL_CLI_TESTS else {}
    report["legacy"] = {"tests": list(LEGACY_TESTS), "resolved": legacy,
                        "unresolved": [t for t, n in legacy.items() if not n],
                        "run": runner(LEGACY_TESTS) if run and LEGACY_TESTS else None}
    report["no_real_cli"] = {"tests": list(NO_REAL_CLI_TESTS), "resolved": no_cli,
                             "unresolved": [t for t, n in no_cli.items() if not n],
                             "run": runner(NO_REAL_CLI_TESTS) if run and NO_REAL_CLI_TESTS else None}
    report["unresolved"] = sorted({tid for c in report["contracts"] for cell in c["cells"].values()
                                   for tid in cell["unresolved"]}
                                  | set(report["legacy"]["unresolved"])
                                  | set(report["no_real_cli"]["unresolved"]))
    report["failed"] = sorted(
        f"{c['id']}/{h}" for c in report["contracts"] for h, cell in c["cells"].items()
        if cell["run"] and not cell["run"]["ok"]
    )
    for extra in ("legacy", "no_real_cli"):
        if report[extra]["run"] and not report[extra]["run"]["ok"]:
            report["failed"].append(extra)
    return report


# ---- packaging review --------------------------------------------------------------------------

_SHA_PIN = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", re.M)
_HEX40 = re.compile(r"@[0-9a-f]{40}$")


def _strip_yaml_comments(text):
    """Drop full-line and trailing `#` comments so prose about a credential is not read as a
    grant of one. Not a YAML parser: a `#` inside a quoted scalar would be cut too, and the
    workflow this reviews carries none."""
    kept = []
    for line in text.splitlines():
        if line.strip().startswith("#"):
            continue
        kept.append(re.sub(r"\s+#.*$", "", line))
    return "\n".join(kept) + "\n"


def _review_workflow(text, findings, rel):
    text = _strip_yaml_comments(text)
    for match in _SHA_PIN.finditer(text):
        ref = match.group(1)
        if not _HEX40.search(ref):
            findings.append(f"{rel}: action {ref!r} is not pinned to a full commit SHA")
    top = re.search(r"^permissions:\n((?:[ \t]+.*\n)+)", text, re.M)
    if not top:
        findings.append(f"{rel}: no top-level permissions block")
    else:
        grants = [ln.strip() for ln in top.group(1).splitlines() if ln.strip()]
        if grants != ["contents: read"]:
            findings.append(f"{rel}: top-level permissions are {grants}, expected ['contents: read']")
    head, sep, _deploy = text.partition("\n  deploy:")
    if not sep:
        findings.append(f"{rel}: no deploy job")
    for credential in ("pages: write", "id-token: write"):
        if credential in head:
            findings.append(f"{rel}: {credential!r} appears outside the deploy job")


def _review_requirements(text, findings, rel):
    joined = text.replace("\\\n", " ")
    for line in joined.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        if "==" in line and "--hash=sha256:" not in line:
            findings.append(f"{rel}: {line.split('==')[0]!r} carries no sha256 hash")


def packaging_review(repo_root=REPO_ROOT, tracked=None):
    """Findings (fail the gate) and notes (informational) about what the package carries."""
    root = Path(repo_root)
    rd = _sibling("runtime_data")
    findings, notes = [], []
    try:
        gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    except OSError:
        gitignore = ""
    rules = {ln.strip() for ln in gitignore.splitlines() if ln.strip() and not ln.startswith("#")}
    stores = {}
    for name in rd.STORES:
        rule = f"/{name}/"
        stores[name] = rule in rules
        if rule not in rules:
            findings.append(f".gitignore: store {name!r} has no root-anchored rule {rule!r}")
    if "/value-report*.html" not in rules:
        findings.append(".gitignore: generated value reports are not ignored")

    if tracked is None:
        tracked = tracked_paths(root)
    inventory = {}
    if tracked is None:
        notes.append("git could not list tracked files; tracked-path checks skipped")
        tracked = []
    for path in tracked:
        top = path.split("/", 1)[0]
        inventory[top] = inventory.get(top, 0) + 1
        for store in rd.STORES:
            if path.startswith(f"{store}/"):
                findings.append(f"tracked: {path} lies under the private store {store!r}")
        for needle, why in FORBIDDEN_TRACKED:
            if needle in path:
                findings.append(f"tracked: {path} ({why})")
    for top in sorted(inventory):
        if top not in TREE_ROLES:
            findings.append(f"tracked: top-level {top!r} has no role in the package inventory")

    versions = package_versions(root)
    plugin, market = versions["plugin"], versions["marketplace"]
    if not plugin["version"] or not _SEMVER.match(str(plugin["version"])):
        findings.append(f".claude-plugin/plugin.json: version {plugin['version']!r} is not MAJOR.MINOR.PATCH")
    entries = [p for p in market["plugins"] if p["name"] == plugin["name"]]
    if not entries:
        findings.append(f".claude-plugin/marketplace.json: no plugin entry named {plugin['name']!r}")
    elif entries[0]["description"] != plugin["description"]:
        findings.append(".claude-plugin/marketplace.json: the plugin description differs from plugin.json")
    codex = versions["codex_plugin"]
    if codex["name"] and codex["name"] != plugin["name"]:
        findings.append(f".codex-plugin/plugin.json: name {codex['name']!r} differs from {plugin['name']!r}")
    if codex["name"] and codex["name"] not in versions["codex_marketplace"]["plugins"]:
        findings.append(".agents/plugins/marketplace.json: the Codex plugin is not listed")
    if codex["version"] and plugin["version"] and not str(codex["version"]).startswith(str(plugin["version"])):
        notes.append(f"the Codex package version {codex['version']!r} does not start with the plugin "
                     f"version {plugin['version']!r}; both are bumped by hand at release")

    workflows = sorted((root / ".github" / "workflows").glob("*.yml"))
    if not workflows:
        notes.append("no GitHub workflow present")
    for wf in workflows:
        _review_workflow(wf.read_text(encoding="utf-8"), findings, wf.relative_to(root).as_posix())
    req = root / "docs-src" / "requirements.txt"
    if req.is_file():
        _review_requirements(req.read_text(encoding="utf-8"), findings, "docs-src/requirements.txt")
    else:
        notes.append("docs-src/requirements.txt absent")

    return {
        "schema": GATE_VERSION,
        "stores": stores,
        "inventory": {top: {"tracked": n, "role": TREE_ROLES.get(top)} for top, n in sorted(inventory.items())},
        "findings": findings,
        "notes": notes,
    }


# ---- registry consistency and re-verification --------------------------------------------------

def registry_findings(repo_root=REPO_ROOT):
    """What the registry must satisfy for a release: every advertised harness present, every
    row well-formed, every capability the contract table names present, and a verification
    dated since this gate carrying the client version it was made against."""
    ha, registry = _registry(repo_root)
    findings = []
    for harness in HARNESSES:
        entry = registry["harnesses"].get(harness)
        if not entry:
            findings.append(f"registry: harness {harness!r} has no rows")
            continue
        rows = entry.get("capabilities") or {}
        for name, raw in rows.items():
            try:
                ha.capability(name, product=raw.get("product", ha.UNKNOWN),
                              implemented=raw.get("implemented", ha.UNKNOWN),
                              verified=raw.get("verified", ha.UNKNOWN),
                              verified_on=raw.get("verified_on"))
            except ValueError as exc:
                findings.append(f"registry: {harness}/{name}: {exc}")
                continue
            if (harness != "stub" and raw.get("verified") == ha.SUPPORTED
                    and str(raw.get("verified_on") or "") >= CLIENT_VERSION_REQUIRED_FROM
                    and not raw.get("client_version")):
                findings.append(
                    f"registry: {harness}/{name} verified on {raw.get('verified_on')} names no "
                    f"client_version; a verification since {CLIENT_VERSION_REQUIRED_FROM} records the "
                    f"client it ran against"
                )
        for contract in CONTRACTS:
            for name in contract["capabilities"].get(harness, ()):
                if name not in rows:
                    findings.append(f"registry: {harness} has no {name!r} row, which the "
                                    f"{contract['id']} contract cites")
    return findings


def reverify(harness, released_on, repo_root=REPO_ROOT):
    """What a client release dated `released_on` invalidates for `harness`, and what to run.
    Lists; edits nothing."""
    matrix = harness_matrix(repo_root, with_binaries=True)
    if harness not in matrix or not matrix[harness]["in_registry"]:
        raise ValueError(f"unknown harness {harness!r}; choose from {HARNESSES}")
    entry = matrix[harness]
    stale, first, unsupported, current = [], [], [], []
    for row in entry["capabilities"]:
        if row["verified"] == "supported":
            (stale if (row["verified_on"] or "") < released_on else current).append(row)
        elif row["verified"] == "unsupported":
            unsupported.append(row)
        else:
            first.append(row)
    facts = HARNESS_FACTS[harness]
    commands = ["python3 bin/harness_update.py check"]
    if harness in DRIVER_MODULES:
        commands.append(f"python3 {facts['driver'].split(' ')[0]} run --kit DIR --dry-run")
    if harness == "cursor":
        commands.append("python3 bin/harness_select.py doctor --harness cursor --project DIR")
    commands.append(f"python3 bin/workflow_eval.py plan --repo DIR --harness "
                    f"{'claude' if harness == 'claude-code' else harness} --models M --repeats 2")
    return {
        "harness": harness,
        "released_on": released_on,
        "binary": entry["binary"],
        "revalidate": [r["name"] for r in stale],
        "first_verification": [r["name"] for r in first],
        "recheck_unsupported": [r["name"] for r in unsupported],
        "still_current": [r["name"] for r in current],
        "commands": commands,
        "record": "edit the row by hand: verified, verified_on, client_version, and the command "
                  "that produced the answer in its note; this tool writes nothing",
    }


# ---- renderers ---------------------------------------------------------------------------------

def _table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) if c is not None else "" for c in row) + " |")
    return "\n".join(lines)


def _code(text):
    return f"`{text}`" if text else ""


def render_versions(versions, contracts):
    out = ["### Versions", "",
           "Contract versions are read from the module that owns each one; package versions "
           "from the manifests; `cached_date` from each pricing file.", ""]
    out.append(_table(("Contract", "Owner", "Version"),
                      [(r["contract"], _code(r["owner"]), _code(r["version"])) for r in contracts]))
    out.append("")
    pkg = [
        ("Claude Code plugin", f"{versions['plugin']['name']} {versions['plugin']['version']}"),
        ("Local marketplace", versions["marketplace"]["name"]),
        ("Codex package", f"{versions['codex_plugin']['name']} {versions['codex_plugin']['version']}"),
        ("Codex marketplace", versions["codex_marketplace"]["name"]),
        ("Capability registry schema", versions["registry_schema"]),
        ("Historical primitive matrix", f"{versions['matrix_schema']} pinned at aesop "
                                        f"{(versions['matrix_pin'] or '')[:12]} ({versions['matrix_verified']})"),
        ("Primitive model schema", versions["primitive_model_schema"]),
        ("Site toolchain (locked)", ", ".join(f"{k} {v}" for k, v in sorted(versions["toolchain"].items()))
                                    or "not pinned"),
        ("Python floor", (versions["python_floor"] or "unknown") + " (stdlib only)"),
    ]
    out.append(_table(("Package", "Version"), pkg))
    out.append("")
    out.append(_table(("Harness", "Pricing file", "cached_date", "Models"),
                      [(h, _code(p["file"]), p["cached_date"], p["models"])
                       for h, p in versions["pricing"].items()]))
    return "\n".join(out)


def render_matrix(matrix):
    out = ["### Operational support by harness", "",
           "Three answers per capability, never collapsed: does the product support it, has "
           "polytropos implemented it, has anyone run it on a real client and dated the run. "
           "`Client version` is what that run recorded; `not recorded` means no verification has "
           "named one. A stub's `supported` rows are about the stub.", ""]
    summary = []
    for harness in HARNESSES:
        e = matrix[harness]
        summary.append((
            e["label"], _code(e["driver"]), _code(e["binary"]) if e["binary"] else "none",
            e["client_mode"], e["client_version"],
            e["latest_evidence"] or "none",
            f"{len(e['verified_supported'])} verified / {len(e['unknown'])} unknown / "
            f"{len(e['unsupported'])} unsupported",
        ))
    out.append(_table(("Harness", "Driver", "Binary", "Client mode", "Client version",
                       "Latest evidence", "Rows"), summary))
    out.append("")
    for harness in HARNESSES:
        e = matrix[harness]
        out.append(f"#### {e['label']}")
        out.append("")
        facts = [
            f"- Install: {_code(e['install']) if e['install'] else 'not installable; a conformance target'}",
            f"- Bundle: {_code(e['bundle']) if e['bundle'] else 'none'}",
            f"- Review form: {e['review_form']}",
            f"- Pricing: {_code(e['pricing_file']) if e['pricing_file'] else 'none'}"
            + (f" (`cached_date` {e['pricing_cached_date']}, {e['roster_models']} models)"
               if e["pricing_file"] else ""),
            f"- Evaluation adapter: {_code(e['eval_adapter'])}",
        ]
        out.extend(facts)
        out.append("")
        out.append(_table(("Capability", "Product", "Implemented", "Verified", "On", "Client", "Effective"),
                          [(r["name"], r["product"], r["implemented"], r["verified"],
                            r["verified_on"] or "", r.get("client_version") or "", r["effective"])
                           for r in e["capabilities"]]))
        out.append("")
    return "\n".join(out).rstrip()


def render_roles(matrix):
    kc = _sibling("kit_contract")
    roles = list(kc.ROLE_CONTRACTS)
    out = ["### Role support by harness", "",
           "From `kit_contract.ROLE_SUPPORT`: `sequenced` means the driver runs the role in its "
           "loop, `partial` means part of the role's job runs without an agent, `unsupported` "
           "means a kit that declares it is refused or disclosed before dispatch.", ""]
    rows = []
    for role in roles:
        rows.append((role,) + tuple(matrix[h]["role_support"].get(role, "") for h in HARNESSES))
    out.append(_table(("Role",) + tuple(matrix[h]["label"].split(" (")[0] for h in HARNESSES), rows))
    return "\n".join(out)


def render_contracts(report):
    out = ["### Shared contracts: stub conformance beside installed-client verification", "",
           "Left column per harness: the tests that drive the driver through a stub executable "
           "and a temp store, with how many test cases each id resolves to. Right column: the "
           "registry rows a real client would have to verify, and their state. A contract with "
           "no registry row is polytropos's own, and the stub column is the whole of its "
           "evidence.", ""]
    for c in report["contracts"]:
        out.append(f"#### {c['title']} (steps {c['steps']})")
        out.append("")
        out.append(c["claim"] + ".")
        out.append("")
        rows = []
        for harness in HARNESSES + (SHARED,):
            cell = c["cells"][harness]
            if not cell["tests"] and harness != SHARED and cell["installed_client"] is None:
                continue
            tests = "; ".join(f"`{tid}` ({cell['resolved'].get(tid, 0)})" for tid in cell["tests"]) or "none mapped"
            if cell["run"]:
                r = cell["run"]
                tests += f" -- ran {r['ran']}, {'OK' if r['ok'] else 'FAILED'}"
            installed = cell["installed_client"]
            if installed is None:
                verdict = "n/a"
            elif installed["rows"]:
                verdict = installed["verdict"] + ": " + ", ".join(
                    f"{r['name']}={r['verified']}" for r in installed["rows"])
            else:
                verdict = installed["verdict"]
            rows.append((harness, tests, verdict))
        out.append(_table(("Harness", "Stub conformance", "Installed client"), rows))
        out.append("")
    out.append("#### Legacy kits")
    out.append("")
    out.append("; ".join(f"`{t}` ({report['legacy']['resolved'].get(t, 0)})" for t in report["legacy"]["tests"])
               or "none mapped")
    out.append("")
    out.append("#### No real client is ever spawned")
    out.append("")
    out.append("; ".join(f"`{t}` ({report['no_real_cli']['resolved'].get(t, 0)})"
                         for t in report["no_real_cli"]["tests"]) or "none mapped")
    return "\n".join(out)


def render_historical(hist):
    out = ["### Historical primitive matrix (unchanged)", "",
           f"`primitives/harness-matrix.json` ({hist['schema']}) is aesop's product-support "
           f"matrix pinned at commit `{(hist['pin'] or '')[:12]}` ({hist['verified']}). It answers "
           "\"does the product have this primitive\", not \"can a driver rely on it\", and it is "
           "not rewritten by this gate.", ""]
    out.append(_table(("Harness", "Goal mode", "Native", "Fallback"),
                      [(r["harness"], r["goal_mode"], ", ".join(r["native"]) or "none",
                        ", ".join(r["fallback"]) or "none") for r in hist["rows"]]))
    return "\n".join(out)


def render_packaging_roles(review):
    out = ["### What the package carries", "",
           "Every top-level tracked path and its role. `packaging` fails on a path with no "
           "role, a tracked file under a private store, or a store without its root-anchored "
           "ignore rule.", ""]
    out.append(_table(("Path", "Role"), [(_code(p), r) for p, r in sorted(TREE_ROLES.items())]))
    out.append("")
    out.append(_table(("Private store", "Ignore rule"),
                      [(_code(name + "/"), "present" if ok else "MISSING")
                       for name, ok in sorted(review["stores"].items())]))
    return "\n".join(out)


def render_checklist():
    out = ["### Release checklist", "",
           "Each guarantee names the evidence behind it and what stays unresolved. Every "
           "command below is resolved by `check`, so a renamed subcommand fails the gate.", ""]
    out.append(_table(("Guarantee", "Evidence", "Unresolved"),
                      [(c["guarantee"], c["evidence"], c["limit"]) for c in CHECKLIST]))
    return "\n".join(out)


def render_migration():
    out = ["### Migration and rollback", ""]
    out.append(_table(("Surface", "Forward", "Back"),
                      [(m["surface"], m["forward"], m["back"]) for m in MIGRATION_NOTES]))
    return "\n".join(out)


def render_triggers():
    out = ["### What a new harness or model release triggers", "",
           "Targeted re-evaluation, never automatic: nothing below edits a registry row, adds a "
           "permanent instruction, or promotes a routing default.", ""]
    out.append(_table(("Trigger", "Do", "Never"),
                      [(t["trigger"], t["do"], t["never"]) for t in REEVALUATION_TRIGGERS]))
    return "\n".join(out)


def render_prepared():
    out = ["### Prepared, not run", "",
           "Each of these contacts a vendor with the user's own credentials or spends. They are "
           "written out so that running one is a decision, not an improvisation; the registry "
           "rows each one names say whether, when, and on which client it has run.", ""]
    for p in PREPARED_COMMANDS:
        out.append(f"**{p['name']}.** Records: {p['records']}.")
        out.append("")
        out.append("```bash")
        out.append(p["command"])
        out.append(f"# then, on your own account: {p['then']}")
        out.append("```")
        out.append("")
    return "\n".join(out).rstrip()


def render_block(repo_root=REPO_ROOT):
    """The deterministic generated block for docs/RELEASE.md."""
    matrix = harness_matrix(repo_root)
    parts = [
        BLOCK_START,
        "<!-- Generated by `python3 bin/release_gate.py build` from the capability registry, the "
        "contract map, the manifests, and the pricing files. Do not edit by hand; "
        "`release_gate.py check` fails on drift. -->",
        "",
        render_versions(package_versions(repo_root), contract_versions()),
        "",
        render_matrix(matrix),
        "",
        render_roles(matrix),
        "",
        render_contracts(contracts_report(repo_root)),
        "",
        render_historical(historical_matrix(repo_root)),
        "",
        render_packaging_roles(packaging_review(repo_root, tracked=[])),
        "",
        render_checklist(),
        "",
        render_migration(),
        "",
        render_triggers(),
        "",
        render_prepared(),
        "",
        BLOCK_END,
    ]
    return "\n".join(parts) + "\n"


def _split_doc(text):
    start = text.find(BLOCK_START)
    end = text.find(BLOCK_END)
    if start < 0 or end < 0 or end < start:
        raise ValueError(f"{RELEASE_DOC} must carry {BLOCK_START} before {BLOCK_END}")
    end += len(BLOCK_END)
    if end < len(text) and text[end] == "\n":
        end += 1
    return text[:start], text[end:]


def build_release_doc(repo_root=REPO_ROOT):
    """Rewrite the marked block of docs/RELEASE.md -> whether it changed."""
    path = Path(repo_root) / RELEASE_DOC
    text = path.read_text(encoding="utf-8")
    head, tail = _split_doc(text)
    new = head + render_block(repo_root) + tail
    if new == text:
        return False
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(new, encoding="utf-8")
    tmp.replace(path)
    return True


def check_release_doc(repo_root=REPO_ROOT):
    """-> a finding string, or None when the block is current."""
    path = Path(repo_root) / RELEASE_DOC
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return f"{RELEASE_DOC} is missing"
    try:
        head, tail = _split_doc(text)
    except ValueError as exc:
        return str(exc)
    if head + render_block(repo_root) + tail != text:
        return f"{RELEASE_DOC}: the generated block is stale; run `python3 bin/release_gate.py build`"
    return None


# ---- commands the checklist names must exist ---------------------------------------------------

_CMD = re.compile(r"`python3 (bin/[a-z_]+\.py)(?: ([a-z][a-z-]*))?")


def checklist_commands():
    """Every `python3 bin/X.py sub` the checklist, migration notes, triggers, and prepared
    commands mention -> [(script, subcommand)]."""
    texts = []
    for c in CHECKLIST:
        texts.extend((c["evidence"], c["limit"]))
    for m in MIGRATION_NOTES:
        texts.extend((m["forward"], m["back"]))
    for t in REEVALUATION_TRIGGERS:
        texts.extend((t["do"], t["never"]))
    for p in PREPARED_COMMANDS:
        texts.append("`" + p["command"] + "`")
    found = set()
    for text in texts:
        for script, sub in _CMD.findall(text):
            found.add((script, sub or None))
    return sorted(found)


def _subcommands(module):
    build = getattr(module, "build_parser", None)
    if build is None:
        return None
    try:
        parser = build()
    except Exception:  # noqa: BLE001 -- a parser that cannot build is "unknown", not a crash here
        return None
    for action in parser._actions:
        choices = getattr(action, "choices", None)
        if isinstance(choices, dict):
            return set(choices)
    return set()


def command_findings(repo_root=REPO_ROOT):
    """A named script must exist; a named subcommand must be one its parser knows (when the
    script exposes `build_parser`)."""
    findings = []
    root = Path(repo_root)
    for script, sub in checklist_commands():
        path = root / script
        if not path.is_file():
            findings.append(f"checklist names {script}, which does not exist")
            continue
        if sub is None:
            continue
        subs = _subcommands(_sibling(path.stem))
        if subs is None:
            continue
        if subs and sub not in subs:
            findings.append(f"checklist names `{script} {sub}`, but its parser knows {sorted(subs)}")
    return findings


# ---- the gate ----------------------------------------------------------------------------------

def run_check(repo_root=REPO_ROOT, run_contracts=False):
    """Everything a release must satisfy, as one report. Exit 3 on any finding."""
    findings = []
    findings.extend(registry_findings(repo_root))
    contracts = contracts_report(repo_root, run=run_contracts)
    findings.extend(f"contract test id resolves to no test: {tid}" for tid in contracts["unresolved"])
    findings.extend(f"contract tests failed: {cell}" for cell in contracts["failed"])
    packaging = packaging_review(repo_root)
    findings.extend(packaging["findings"])
    findings.extend(command_findings(repo_root))
    doc = check_release_doc(repo_root)
    if doc:
        findings.append(doc)
    return {
        "schema": GATE_VERSION,
        "revision": revision(repo_root),
        "checked_on": str(date.today()),
        "findings": findings,
        "notes": packaging["notes"],
        "contracts_run": run_contracts,
        "exit": EXIT_DRIFT if findings else EXIT_OK,
    }


def render_check(result):
    rev = result["revision"]
    lines = [f"release gate ({GATE_VERSION}) on {rev['sha'] or 'no revision'}"
             + (f" ({rev['committed_on']}, {rev['dirty']} dirty)" if rev["sha"] else "")
             + f", checked {result['checked_on']}"]
    lines.append(f"contracts run: {'yes' if result['contracts_run'] else 'no (ids resolved only; --run runs them)'}")
    if result["findings"]:
        lines.append(f"FINDINGS ({len(result['findings'])}):")
        lines.extend(f"  - {f}" for f in result["findings"])
    else:
        lines.append("findings: none")
    for note in result["notes"]:
        lines.append(f"note: {note}")
    lines.append("verdict: " + ("DRIFT (exit 3)" if result["findings"] else "OK"))
    return "\n".join(lines)


# ---- CLI ---------------------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        prog="release_gate.py",
        description="The release matrix, the shared-contract evidence table, the packaging "
                    "review, and the release checklist, computed from the records that carry "
                    "them. Spawns nothing but read-only git; edits nothing but the marked block "
                    "of docs/RELEASE.md on `build`.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("matrix", help="operational support per harness, from the registry")
    m.add_argument("--json", action="store_true")
    c = sub.add_parser("contracts", help="stub conformance beside installed-client verification")
    c.add_argument("--run", action="store_true", help="run the mapped tests in-process")
    c.add_argument("--json", action="store_true")
    pk = sub.add_parser("packaging", help="what the package carries; findings fail")
    pk.add_argument("--json", action="store_true")
    sub.add_parser("checklist", help="the release checklist, migration notes, triggers, and prepared commands")
    rv = sub.add_parser("reverify", help="what a client release invalidates; edits nothing")
    rv.add_argument("--harness", required=True, choices=HARNESSES)
    rv.add_argument("--released", required=True, help="the release date, YYYY-MM-DD")
    rv.add_argument("--json", action="store_true")
    ck = sub.add_parser("check", help="the gate: registry, contract ids, packaging, commands, doc block (exit 3 on drift)")
    ck.add_argument("--run", action="store_true", help="also run every mapped test in-process")
    ck.add_argument("--json", action="store_true")
    sub.add_parser("build", help="rewrite the marked block of docs/RELEASE.md")
    for node in (m, c, pk, rv, ck):
        node.add_argument("--repo-root", default=str(REPO_ROOT))
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    root = Path(getattr(args, "repo_root", str(REPO_ROOT)))
    if args.cmd == "matrix":
        matrix = harness_matrix(root)
        if args.json:
            print(json.dumps({"schema": GATE_VERSION, "harnesses": matrix}, indent=2, sort_keys=True))
        else:
            print(render_versions(package_versions(root), contract_versions()))
            print()
            print(render_matrix(matrix))
            print()
            print(render_roles(matrix))
        return EXIT_OK
    if args.cmd == "contracts":
        report = contracts_report(root, run=args.run)
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(render_contracts(report))
            if report["unresolved"]:
                print("\nUNRESOLVED: " + ", ".join(report["unresolved"]))
            if report["failed"]:
                print("\nFAILED: " + ", ".join(report["failed"]))
        return EXIT_DRIFT if report["unresolved"] or report["failed"] else EXIT_OK
    if args.cmd == "packaging":
        review = packaging_review(root)
        if args.json:
            print(json.dumps(review, indent=2, sort_keys=True))
        else:
            print(render_packaging_roles(review))
            print()
            for f in review["findings"]:
                print(f"FINDING: {f}")
            for n in review["notes"]:
                print(f"note: {n}")
            print("verdict: " + ("DRIFT (exit 3)" if review["findings"] else "OK"))
        return EXIT_DRIFT if review["findings"] else EXIT_OK
    if args.cmd == "checklist":
        print("\n\n".join((render_checklist(), render_migration(), render_triggers(), render_prepared())))
        return EXIT_OK
    if args.cmd == "reverify":
        try:
            report = reverify(args.harness, args.released, root)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_ERROR
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(f"{args.harness}: a client release on {args.released} (binary {report['binary'] or 'none'})")
            for key, label in (("revalidate", "verified before the release; run again"),
                               ("first_verification", "never verified; a first run"),
                               ("recheck_unsupported", "unsupported; a release may change it"),
                               ("still_current", "verified since the release")):
                print(f"  {label}: {', '.join(report[key]) or 'none'}")
            print("  run:")
            for cmd in report["commands"]:
                print(f"    {cmd}")
            print(f"  record: {report['record']}")
        return EXIT_OK
    if args.cmd == "check":
        result = run_check(root, run_contracts=args.run)
        print(json.dumps(result, indent=2, sort_keys=True) if args.json else render_check(result))
        return result["exit"]
    if args.cmd == "build":
        changed = build_release_doc(REPO_ROOT)
        print(f"{RELEASE_DOC}: {'rewritten' if changed else 'up to date'}")
        return EXIT_OK
    return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
