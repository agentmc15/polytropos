"""Regression tests for Fable usage accounting in ``bin/agent_tracker.py``."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


BIN = Path(__file__).resolve().parent.parent / "bin" / "agent_tracker.py"


def _load_tracker():
    spec = importlib.util.spec_from_file_location("agent_tracker_test", BIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FablePricingByModelTests(unittest.TestCase):
    def test_mixed_fable_generations_keep_their_own_cache_read_rate(self):
        tracker = _load_tracker()
        pricing = {
            "cache_read_multiplier": 0.1,
            "cache_write_multiplier_5m": 1.25,
            "models": {
                "claude-fable-5-1": {
                    "input_per_mtok": 10.0,
                    "output_per_mtok": 50.0,
                    "cache_read_multiplier": 0.025,
                },
                "claude-fable-5": {
                    "input_per_mtok": 10.0,
                    "output_per_mtok": 50.0,
                },
            },
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            transcript = root / "agent.jsonl"
            transcript.write_text(
                "\n".join((
                    json.dumps({"message": {"model": "claude-fable-5", "usage": {
                        "cache_read_input_tokens": 1_000_000}}}),
                    json.dumps({"message": {"model": "claude-fable-5-1-20260901", "usage": {
                        "cache_read_input_tokens": 1_000_000}}}),
                )) + "\n"
            )
            pricing_path = root / "pricing.json"
            pricing_path.write_text(json.dumps(pricing))
            tracker.STATE_DIR = str(root / "state")
            tracker.PRICING_PATH = str(pricing_path)

            tracker.accumulate_fable("agent-1", str(transcript))

            tally = json.loads(Path(tracker.fable_usage_path()).read_text())

        # The externally stored tally shape stays aggregate, while the cost is the sum of
        # legacy Fable 5 (0.1x) and Fable 5.1 (0.025x): $1.00 + $0.25.
        self.assertEqual(tally["cache_read"], 2_000_000)
        self.assertEqual(tally["in"], 0)
        self.assertEqual(tally["out"], 0)
        self.assertEqual(tally["cache_write"], 0)
        self.assertAlmostEqual(tally["cost"], 1.25)
        self.assertEqual(set(tally), {"dispatches", "in", "out", "cache_read", "cache_write", "cost"})
