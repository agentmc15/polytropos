"""Stdlib unittest regression suite for bin/statusline.py.

Runs the script as a subprocess (it reads stdin and prints one line), per PLAN.md D2.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "bin"
SCRIPT = BIN / "statusline.py"

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(s):
    return ANSI_RE.sub("", s)


def run_statusline(payload, state_dir=None, snapshot_dir=None):
    """payload: dict (JSON-encoded), a raw string, or None (empty stdin).

    state_dir: if given, sets POLYTROPOS_STATE_DIR so the script reads its live-count / Fable-tally
    state from an isolated temp dir instead of the real ~/.claude one.
    snapshot_dir: if given, sets POLYTROPOS_SNAPSHOT_DIR (T11, PLAN D11) so the script reads its
    escalation-alarm verdict from an isolated temp dir instead of the real repo's trends/.
    """
    if payload is None:
        input_str = ""
    elif isinstance(payload, str):
        input_str = payload
    else:
        input_str = json.dumps(payload)
    env = dict(os.environ)
    if state_dir is not None:
        env["POLYTROPOS_STATE_DIR"] = str(state_dir)
    if snapshot_dir is not None:
        env["POLYTROPOS_SNAPSHOT_DIR"] = str(snapshot_dir)
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=input_str,
        capture_output=True,
        text=True,
        env=env,
    )


class StatuslineCoreTests(unittest.TestCase):
    def test_full_payload_renders_all_fields(self):
        payload = {
            "model": {"id": "claude-opus-4-8", "display_name": "Opus 4.8"},
            "effort": {"level": "high"},
            "cost": {"total_cost_usd": 0.5},
            "context_window": {"used_percentage": 85},
            "rate_limits": {
                "five_hour": {"used_percentage": 63},
                "seven_day": {"used_percentage": 22},
            },
        }
        proc = run_statusline(payload)
        out = strip_ansi(proc.stdout)
        self.assertIn("Opus 4.8", out)
        self.assertIn("high", out)
        self.assertIn("$0.50", out)
        self.assertIn("ctx 85%", out)
        self.assertIn("5h 63%", out)
        self.assertIn("7d 22%", out)

    def test_setup_skill_sample_payload_exact_output(self):
        # Matches the sample JSON in skills/setup/SKILL.md's smoke test. It omits
        # session_id, so the segments added after this kit was architected (token
        # total, live agent count, Fable daily tally) stay hidden and this exact
        # string still holds (see NOTES.md).
        payload = {
            "model": {"id": "claude-fable-5", "display_name": "Fable 5"},
            "cost": {"total_cost_usd": 1.23},
            "context_window": {"used_percentage": 42},
        }
        proc = run_statusline(payload)
        out = strip_ansi(proc.stdout).strip()
        self.assertEqual(out, "⬢ Fable 5 | $1.23 | ctx 42%")

    def test_empty_stdin_falls_back(self):
        proc = run_statusline("")
        out = strip_ansi(proc.stdout).strip()
        self.assertEqual(out, "polytropos: no status data")

    def test_invalid_json_falls_back(self):
        proc = run_statusline("not json")
        out = strip_ansi(proc.stdout).strip()
        self.assertEqual(out, "polytropos: no status data")

    def test_model_only_payload_has_no_dollar_sign(self):
        payload = {"model": {"id": "claude-sonnet-5", "display_name": "Sonnet 5"}}
        proc = run_statusline(payload)
        out = strip_ansi(proc.stdout)
        self.assertIn("Sonnet 5", out)
        self.assertNotIn("$", out)


class StatuslineNewSegmentTests(unittest.TestCase):
    """Covers segments statusline.py gained after this kit was architected (token total, live
    '⚡ N agents' count, always-on '🔥 Fable ×N' tally, and the second Fable-token/cost line — see
    NOTES.md). These read GLOBAL state files under POLYTROPOS_STATE_DIR; each test points that at an
    isolated temp dir so results are deterministic and the real state/ dir is never touched."""

    def setUp(self):
        self.state_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.state_dir, ignore_errors=True)

    def test_token_total_segment(self):
        # Gated on context_window carrying total_input_tokens/total_output_tokens, not session_id.
        payload = {
            "model": {"id": "claude-sonnet-5", "display_name": "Sonnet 5"},
            "cost": {"total_cost_usd": 0.5},
            "context_window": {
                "used_percentage": 10,
                "total_input_tokens": 1_500_000,
                "total_output_tokens": 200_000,
            },
        }
        proc = run_statusline(payload)
        out = strip_ansi(proc.stdout)
        self.assertIn("1.7M tok", out)

    def test_agent_count_segment_with_seeded_state(self):
        (self.state_dir / "agents.count").write_text("3")
        payload = {
            "model": {"id": "claude-sonnet-5", "display_name": "Sonnet 5"},
            "cost": {"total_cost_usd": 0.1},
            "session_id": "real-session",
        }
        proc = run_statusline(payload, state_dir=self.state_dir)
        out = strip_ansi(proc.stdout)
        self.assertIn("⚡ 3 agents", out)

    def test_fable_tally_and_cost_line(self):
        day = time.strftime("%Y-%m-%d")
        (self.state_dir / f"fable-usage-{day}.json").write_text(
            json.dumps({"dispatches": 2, "in": 1_000_000, "out": 100_000,
                        "cache_read": 0, "cache_write": 0, "cost": 15.0})
        )
        payload = {
            "model": {"id": "claude-sonnet-5", "display_name": "Sonnet 5"},
            "cost": {"total_cost_usd": 0.1},
            "session_id": "real-session",
        }
        proc = run_statusline(payload, state_dir=self.state_dir)
        out = strip_ansi(proc.stdout)
        self.assertIn("🔥 Fable ×2", out)
        self.assertIn("↳ Fable today: 1.1M tok · $15.00", out)

    def test_fable_tally_defaults_to_zero_in_isolated_state(self):
        payload = {
            "model": {"id": "claude-sonnet-5", "display_name": "Sonnet 5"},
            "cost": {"total_cost_usd": 0.1},
            "session_id": "real-session",
        }
        proc = run_statusline(payload, state_dir=self.state_dir)
        out = strip_ansi(proc.stdout)
        self.assertIn("🔥 Fable ×0", out)
        self.assertIn("↳ Fable today: 0 tok · $0.00", out)

    def test_global_count_does_not_leak_without_session_id(self):
        # A running subagent (global count > 0) must NOT bleed into a session_id-less payload,
        # or the setup-skill exact-match output would break whenever a subagent is live.
        (self.state_dir / "agents.count").write_text("5")
        payload = {
            "model": {"id": "claude-fable-5", "display_name": "Fable 5"},
            "cost": {"total_cost_usd": 1.23},
            "context_window": {"used_percentage": 42},
        }
        proc = run_statusline(payload, state_dir=self.state_dir)
        out = strip_ansi(proc.stdout).strip()
        self.assertEqual(out, "⬢ Fable 5 | $1.23 | ctx 42%")
        self.assertNotIn("⚡", out)
        self.assertNotIn("\U0001F525", out)


class EscalationAlarmSegmentTests(unittest.TestCase):
    """T11 (PLAN D11): the statusline READS bin/routing_scorecard.py's already-computed
    escalation-rate alarm verdict from ``<POLYTROPOS_SNAPSHOT_DIR>/alarm/state.json`` — it
    never recomputes anything itself. Every test here uses an isolated temp
    POLYTROPOS_SNAPSHOT_DIR; the real repo's trends/ dir is never read or written."""

    def setUp(self):
        self.state_dir = Path(tempfile.mkdtemp())
        self.snap_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.state_dir, ignore_errors=True)
        shutil.rmtree(self.snap_dir, ignore_errors=True)

    def _write_alarm(self, alarm_dict):
        alarm_dir = self.snap_dir / "alarm"
        alarm_dir.mkdir(parents=True, exist_ok=True)
        (alarm_dir / "state.json").write_text(json.dumps(alarm_dict))

    def _session_payload(self):
        return {
            "model": {"id": "claude-sonnet-5", "display_name": "Sonnet 5"},
            "cost": {"total_cost_usd": 0.1},
            "session_id": "real-session",
        }

    def test_no_snapshot_store_renders_nothing(self):
        # POLYTROPOS_SNAPSHOT_DIR points at a dir with no alarm/state.json at all.
        proc = run_statusline(self._session_payload(), state_dir=self.state_dir,
                              snapshot_dir=self.snap_dir)
        out = strip_ansi(proc.stdout)
        self.assertNotIn("⚠", out)

    def test_tripped_alarm_renders_compact_segment_with_staleness_date(self):
        self._write_alarm({
            "evaluated": True, "sigma": 1.0, "insufficient_reason": None,
            "baseline": {"kits": 2, "mean": 0.1, "stdev": 0.0, "threshold": 0.1},
            "latest_date": "2026-02-02",
            "tripped": [{"kit": "extra-kits/spike-3", "rate": 0.6667,
                        "with_outcome": 6, "escalated_pass": 4}],
            "no_evidence": ["extra-kits/driver-blind"], "notes": [],
        })
        proc = run_statusline(self._session_payload(), state_dir=self.state_dir,
                              snapshot_dir=self.snap_dir)
        out = strip_ansi(proc.stdout)
        self.assertIn("⚠", out)
        self.assertIn("extra-kits/spike-3", out)
        self.assertIn("67%", out)
        self.assertIn("2026-02-02", out)  # the staleness date, never a live claim

    def test_multiple_tripped_kits_shows_a_plus_n_suffix(self):
        self._write_alarm({
            "evaluated": True, "sigma": 1.0, "insufficient_reason": None,
            "baseline": {"kits": 3, "mean": 0.1, "stdev": 0.0, "threshold": 0.1},
            "latest_date": "2026-02-02",
            "tripped": [
                {"kit": "kit-a", "rate": 0.5, "with_outcome": 4, "escalated_pass": 2},
                {"kit": "kit-b", "rate": 0.4, "with_outcome": 5, "escalated_pass": 2},
            ],
            "no_evidence": [], "notes": [],
        })
        proc = run_statusline(self._session_payload(), state_dir=self.state_dir,
                              snapshot_dir=self.snap_dir)
        out = strip_ansi(proc.stdout)
        self.assertIn("kit-a", out)
        self.assertIn("+1", out)

    def test_evaluated_but_nothing_tripped_renders_nothing(self):
        self._write_alarm({
            "evaluated": True, "sigma": 1.0, "insufficient_reason": None,
            "baseline": {"kits": 2, "mean": 0.1, "stdev": 0.0, "threshold": 0.1},
            "latest_date": "2026-02-02", "tripped": [], "no_evidence": [], "notes": [],
        })
        proc = run_statusline(self._session_payload(), state_dir=self.state_dir,
                              snapshot_dir=self.snap_dir)
        out = strip_ansi(proc.stdout)
        self.assertNotIn("⚠", out)

    def test_insufficient_history_renders_nothing(self):
        self._write_alarm({
            "evaluated": False, "sigma": 1.0,
            "insufficient_reason": "insufficient history — need at least 2 stored "
                                   "snapshots; have 1",
            "baseline": {"kits": 0, "mean": None, "stdev": None, "threshold": None},
            "latest_date": "2026-02-01", "tripped": [], "no_evidence": [], "notes": [],
        })
        proc = run_statusline(self._session_payload(), state_dir=self.state_dir,
                              snapshot_dir=self.snap_dir)
        out = strip_ansi(proc.stdout)
        self.assertNotIn("⚠", out)

    def test_malformed_alarm_json_degrades_to_nothing(self):
        alarm_dir = self.snap_dir / "alarm"
        alarm_dir.mkdir(parents=True, exist_ok=True)
        (alarm_dir / "state.json").write_text("{not valid json")
        proc = run_statusline(self._session_payload(), state_dir=self.state_dir,
                              snapshot_dir=self.snap_dir)
        out = strip_ansi(proc.stdout)
        self.assertNotIn("⚠", out)
        self.assertNotEqual(proc.returncode, None)  # the process still completes cleanly

    def test_alarm_never_appears_without_session_id(self):
        # A tripped alarm on disk must NOT leak into a session_id-less payload -- the
        # setup-skill exact-match precedent (test_setup_skill_sample_payload_exact_output)
        # depends on this the same way it depends on the agent-count/Fable segments.
        self._write_alarm({
            "evaluated": True, "sigma": 1.0, "insufficient_reason": None,
            "baseline": {"kits": 2, "mean": 0.1, "stdev": 0.0, "threshold": 0.1},
            "latest_date": "2026-02-02",
            "tripped": [{"kit": "extra-kits/spike-3", "rate": 0.6667,
                        "with_outcome": 6, "escalated_pass": 4}],
            "no_evidence": [], "notes": [],
        })
        payload = {
            "model": {"id": "claude-fable-5", "display_name": "Fable 5"},
            "cost": {"total_cost_usd": 1.23},
            "context_window": {"used_percentage": 42},
        }
        proc = run_statusline(payload, state_dir=self.state_dir, snapshot_dir=self.snap_dir)
        out = strip_ansi(proc.stdout).strip()
        self.assertEqual(out, "⬢ Fable 5 | $1.23 | ctx 42%")
        self.assertNotIn("⚠", out)


if __name__ == "__main__":
    unittest.main()
