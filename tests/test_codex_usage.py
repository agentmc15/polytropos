"""Stdlib unittest regression suite for bin/codex_usage.py (PLAN.md D8).

SAFETY CONTRACT (binds every test in this file): no test here ever invokes the real ``codex``
CLI, reads or writes the real ``~/.codex``, opens a ``*.db``/SQLite file, or resolves the
caller's real home via ``Path.home``. Every fixture lives under a fresh
``tempfile.TemporaryDirectory()`` codex-home built by this file; rollout / session_index /
history JSONL contents are synthesized in-process; and pricing is a synthetic ``FIXTURE`` dict
with deliberately fake round numbers (``cache_read_multiplier == 0.5``, NOT the real 0.1, and a
``cache_write_multiplier`` that must never surface because writes are never priced), patched
over ``load_pricing`` via ``mock.patch.object(cu, "load_pricing", return_value=FIXTURE)`` -- the
real ``data/pricing.codex.json`` is opened only by the explicitly-labeled structure smoke.

bin/ is not a package; codex_usage.py is loaded via importlib by absolute path computed from
this file's own location (BIN_DIR), mirroring tests/test_copilot_usage.py.
"""

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

BIN_DIR = Path(__file__).resolve().parent.parent / "bin"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, BIN_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cu = _load("codex_usage")


# ---- synthetic fixture --------------------------------------------------------------------
#
# Fake ids and round numbers. cache_read_multiplier == 0.5 (nowhere near the real 0.1) proves
# the cache-read term is derived from the pricing dict at run time, never a hardcoded 0.1;
# cache_write_multiplier == 9.0 must NEVER appear in any priced figure (writes are not
# observable in these logs and are never priced).

FIXTURE = {
    "cached_date": "2020-06-01",
    "cache_read_multiplier": 0.5,
    "cache_write_multiplier": 9.0,
    "models": {
        "fake-front": {
            "display": "Fake Front",
            "vendor": "fake-vendor",
            "tier": "frontier",
            "input_per_mtok": 20.0,
            "output_per_mtok": 100.0,
        },
        "fake-mid": {
            "display": "Fake Mid",
            "vendor": "fake-vendor",
            "tier": "mid",
            "input_per_mtok": 2.0,
            "output_per_mtok": 10.0,
        },
        "fake-cheap": {
            "display": "Fake Cheap",
            "vendor": "fake-vendor",
            "tier": "cheap",
            "input_per_mtok": 1.0,
            "output_per_mtok": 6.0,
        },
    },
}


# ---- record builders ----------------------------------------------------------------------


def _tok_rec(container_key, **fields):
    """A rollout token record: a usage container nested under payload.info (the shape the T1
    peek recorded), so the reader's chained wrapper descent is exercised.
    """
    return {"type": "event_msg", "payload": {"info": {container_key: dict(fields)}}}


def _model_rec(model):
    return {"type": "turn_context", "payload": {"model": model}}


def _lines(records):
    return [json.dumps(r) for r in records]


def _write_rollout(home, records, when=None, name="rollout-x.jsonl"):
    """Write one rollout .jsonl under sessions/YYYY/MM/DD/ for `when` (default now)."""
    when = when or datetime.now(timezone.utc)
    d = home / "sessions" / f"{when:%Y}" / f"{when:%m}" / f"{when:%d}"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text("\n".join(_lines(records)) + "\n")
    return p


def _run_main(home, extra_args=None):
    args = ["--codex-home", str(home)] + (extra_args or [])
    with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cu.main(args)
    return buf.getvalue()


# ---- 1. Cumulative MAX rule ----------------------------------------------------------------


class CumulativeMaxTests(unittest.TestCase):
    def test_three_total_token_usage_snapshots_take_element_wise_max_not_sum(self):
        records = [
            _tok_rec("total_token_usage", input_tokens=100, cached_input_tokens=10, output_tokens=5),
            _tok_rec("total_token_usage", input_tokens=300, cached_input_tokens=20, output_tokens=50),
            # repeated final snapshot (cumulative snapshots re-report the running total)
            _tok_rec("total_token_usage", input_tokens=300, cached_input_tokens=20, output_tokens=50),
        ]
        parsed = cu.parse_rollout(_lines(records))
        # Element-wise MAX; a naive sum would give 700/50/105.
        self.assertEqual(parsed["tokens"], {"input": 300, "cache_read": 20, "output": 50})


# ---- 2. Per-turn SUM rule (and BOTH-kinds -> cumulative MAX only) ---------------------------


class PerTurnSumTests(unittest.TestCase):
    def test_per_turn_usage_containers_are_summed(self):
        records = [
            _tok_rec("usage", input_tokens=100, cached_input_tokens=10, output_tokens=5),
            _tok_rec("usage", input_tokens=50, cached_input_tokens=4, output_tokens=3),
        ]
        parsed = cu.parse_rollout(_lines(records))
        self.assertEqual(parsed["tokens"], {"input": 150, "cache_read": 14, "output": 8})

    def test_both_kinds_in_one_file_use_cumulative_max_only_never_added(self):
        records = [
            _tok_rec("usage", input_tokens=999, cached_input_tokens=999, output_tokens=999),
            _tok_rec("total_token_usage", input_tokens=500, cached_input_tokens=200, output_tokens=20),
            _tok_rec("usage", input_tokens=1, cached_input_tokens=1, output_tokens=1),
        ]
        parsed = cu.parse_rollout(_lines(records))
        # Cumulative wins for the whole file; per-turn 999/1 containers are discarded, never
        # added (a sum would blow past 500/200/20).
        self.assertEqual(parsed["tokens"], {"input": 500, "cache_read": 200, "output": 20})


# ---- 3. reasoning_output_tokens must NOT inflate output ------------------------------------


class ReasoningTokensTests(unittest.TestCase):
    def test_reasoning_output_tokens_are_not_added_to_output(self):
        records = [
            _tok_rec(
                "total_token_usage",
                input_tokens=100,
                output_tokens=40,
                reasoning_output_tokens=1000,  # already inside output_tokens per OpenAI
            )
        ]
        parsed = cu.parse_rollout(_lines(records))
        self.assertEqual(parsed["tokens"]["output"], 40)
        self.assertEqual(parsed["tokens"]["input"], 100)


# ---- 4. Pricing math (cache-read term at the fixture 0.5) + unpriced model ------------------


class PricingMathTests(unittest.TestCase):
    def test_price_tokens_hand_computed_with_cache_read_multiplier(self):
        u = {"input": 1_000_000, "cache_read": 1_000_000, "output": 1_000_000}
        # fake-mid: input 2.0/MTok, cache_read = 2.0 * 0.5 = 1.0/MTok, output 10.0/MTok.
        usd = cu.price_tokens(u, "fake-mid", FIXTURE)
        self.assertAlmostEqual(usd, 2.0 + 1.0 + 10.0)

    def test_cache_read_term_uses_fixture_half_not_real_tenth(self):
        # Only cache_read tokens -> pure cache-read term = input_per_mtok * 0.5.
        u = {"input": 0, "cache_read": 2_000_000, "output": 0}
        usd = cu.price_tokens(u, "fake-mid", FIXTURE)
        self.assertAlmostEqual(usd, 2_000_000 * 2.0 * 0.5 / 1e6)  # == 2.0, not 0.4 (0.1x)

    def test_unmatched_model_lands_in_unpriced_list_with_no_dollars(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            _write_rollout(
                home,
                [_model_rec("fake-mid"),
                 _tok_rec("total_token_usage", input_tokens=1000, output_tokens=100)],
                name="rollout-mapped.jsonl",
            )
            _write_rollout(
                home,
                [_model_rec("unmapped-experimental"),
                 _tok_rec("total_token_usage", input_tokens=5000, output_tokens=500)],
                name="rollout-unmapped.jsonl",
            )
            out = _run_main(home, ["--days", "2"])
        self.assertIn("Unpriced models", out)
        self.assertIn("unmapped-experimental", out)
        # The mapped model IS priced; the unmapped id carries no dollar figure of its own
        # (it appears only in the unpriced list, never in the spend-by-model table).
        self.assertIn("Fake Mid", out)


# ---- 5. Date pruning: out-of-window YYYY/MM/DD dir is never opened --------------------------


class DatePruningTests(unittest.TestCase):
    def test_out_of_window_date_dir_is_pruned_before_open(self):
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=100)
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            in_path = _write_rollout(
                home,
                [_tok_rec("total_token_usage", input_tokens=1, output_tokens=1)],
                when=now,
                name="rollout-in.jsonl",
            )
            out_path = _write_rollout(
                home,
                [_tok_rec("total_token_usage", input_tokens=1, output_tokens=1)],
                when=old,
                name="rollout-out.jsonl",
            )
            cutoff = now - timedelta(days=2)
            yielded = [p.name for p in cu.iter_rollout_files(home / "sessions", cutoff)]
        self.assertIn(in_path.name, yielded)
        self.assertNotIn(out_path.name, yielded)

    def test_out_of_window_tokens_never_priced_in_report(self):
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=100)
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            _write_rollout(
                home,
                [_model_rec("fake-mid"),
                 _tok_rec("total_token_usage", input_tokens=100, output_tokens=10)],
                when=now,
                name="rollout-in.jsonl",
            )
            _write_rollout(
                home,
                [_model_rec("fake-front"),
                 _tok_rec("total_token_usage", input_tokens=9_000_000, output_tokens=9_000_000)],
                when=old,
                name="rollout-out.jsonl",
            )
            out = _run_main(home, ["--days", "2"])
        # The in-window mid model is priced; the out-of-window frontier one never is.
        self.assertIn("Fake Mid", out)
        self.assertNotIn("Fake Front", out)


# ---- 6. Honesty branches -------------------------------------------------------------------


class HonestyBranchTests(unittest.TestCase):
    def test_tokens_branch_prints_verbatim_proxy_disclaimer_and_dollars(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            _write_rollout(
                home,
                [_model_rec("fake-mid"),
                 _tok_rec("total_token_usage", input_tokens=100000, cached_input_tokens=50000,
                          output_tokens=20000)],
                name="rollout-priced.jsonl",
            )
            out = _run_main(home, ["--days", "2"])
        self.assertIn(cu.PROXY_DISCLAIMER, out)
        self.assertIn(
            "Figures are API-equivalent dollars — a relative-burn proxy. Subscription "
            "(ChatGPT-plan) usage is usage-limited, not token-billed.",
            out,
        )
        self.assertIn("$", out)

    def test_activity_only_branch_prints_verbatim_unpriced_line(self):
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / "history.jsonl").write_text(
                json.dumps({"session_id": "s1", "ts": int(now.timestamp()), "text": "x"}) + "\n"
            )
            out = _run_main(home, ["--days", "2"])
        self.assertIn(cu.UNPRICED_NOTE, out)
        self.assertIn("no token usage found in these logs — activity counted, unpriced", out)
        # No fabricated or zeroed dollar stand-in in the activity-only branch.
        self.assertNotIn("$", out)

    def test_empty_home_exits_zero_with_absence_message(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)  # exists but holds no codex logs
            # main() returns normally (no SystemExit / exit 0) on an empty home.
            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    result = cu.main(["--codex-home", str(home)])
                out = buf.getvalue()
        self.assertIsNone(result)
        self.assertIn("No Codex usage data found", out)


# ---- 7. Robustness: malformed / non-dict records, epoch-millis + ISO timestamps ------------


class RobustnessTests(unittest.TestCase):
    def test_malformed_and_non_dict_rollout_records_counted_and_skipped(self):
        lines = [
            "",
            "   ",
            "not valid json {{{",
            "[1, 2, 3]",  # valid JSON but not a dict
            json.dumps(_tok_rec("total_token_usage", input_tokens=42, output_tokens=7)),
        ]
        parsed = cu.parse_rollout(lines)  # must not raise
        self.assertEqual(parsed["malformed"], 2)  # the garbage line + the JSON array
        self.assertEqual(parsed["records"], 1)  # the one real dict record
        self.assertEqual(parsed["tokens"], {"input": 42, "cache_read": 0, "output": 7})

    def test_epoch_millis_and_iso_timestamps_both_parse(self):
        iso = cu.parse_timestamp("2026-06-30T10:00:00Z")
        self.assertIsNotNone(iso)
        self.assertEqual(iso.tzinfo, timezone.utc)
        millis = cu.parse_timestamp(1_700_000_000_000)  # > 1e12 -> milliseconds
        secs = cu.parse_timestamp(1_700_000_000)
        self.assertIsNotNone(millis)
        self.assertIsNotNone(secs)
        # ms and the equivalent seconds resolve to the same instant.
        self.assertEqual(millis, secs)
        self.assertIsNone(cu.parse_timestamp("not-a-timestamp"))
        self.assertIsNone(cu.parse_timestamp(None))

    def test_activity_scan_counts_iso_and_epoch_records_skips_garbage(self):
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            path = home / "session_index.jsonl"
            path.write_text(
                "\n".join([
                    json.dumps({"id": "a", "updated_at": now.isoformat()}),
                    json.dumps({"id": "b", "ts": int(now.timestamp() * 1000)}),  # epoch-millis
                    "garbage not json",
                    "[1,2,3]",
                ]) + "\n"
            )
            cutoff = now - timedelta(days=2)
            sids, models, records, malformed = cu.scan_activity_file(path, cutoff)
        self.assertEqual(records, 2)
        self.assertEqual(sids, {"a", "b"})
        self.assertEqual(malformed, 2)


# ---- 8. Read-only proof (incl. a junk *.db that must never be opened) ----------------------


class ReadOnlyProofTests(unittest.TestCase):
    def test_temp_home_file_tree_byte_identical_after_run(self):
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / "session_index.jsonl").write_text(
                json.dumps({"id": "s1", "updated_at": now.isoformat()}) + "\n"
            )
            (home / "history.jsonl").write_text(
                json.dumps({"session_id": "s1", "ts": int(now.timestamp()), "text": "x"}) + "\n"
            )
            _write_rollout(
                home,
                [_model_rec("fake-mid"),
                 _tok_rec("total_token_usage", input_tokens=1000, cached_input_tokens=100,
                          output_tokens=200)],
                name="rollout-ro.jsonl",
            )
            # A junk SQLite-shaped store -- must NEVER be opened (D8 / OUT-OF-SCOPE fence).
            (home / "logs_2.sqlite").write_bytes(b"\x00NOT-A-REAL-DB\x01junk\x02")

            def snapshot():
                files = sorted(p for p in home.rglob("*") if p.is_file())
                return [str(p) for p in files], {str(p): p.read_bytes() for p in files}

            before_paths, before_bytes = snapshot()
            _run_main(home, ["--days", "2"])
            after_paths, after_bytes = snapshot()

        self.assertEqual(before_paths, after_paths)
        self.assertEqual(before_bytes, after_bytes)


# ---- 9. Structure smoke against the REAL pricing file (no fabricated numbers asserted) ------


class RealPricingStructureSmokeTests(unittest.TestCase):
    """Loads data/pricing.codex.json to prove the reader's field contract matches the real
    file -- structure only, never asserting a specific real dollar amount.
    """

    def test_real_pricing_has_required_fields_and_prices_a_real_model(self):
        pricing = cu.load_pricing()  # the REAL data/pricing.codex.json
        self.assertIn("cache_read_multiplier", pricing)
        self.assertIn("cached_date", pricing)
        self.assertTrue(pricing["models"])
        model_id = next(iter(pricing["models"]))
        row = pricing["models"][model_id]
        self.assertIn("input_per_mtok", row)
        self.assertIn("output_per_mtok", row)
        self.assertIn("display", row)
        self.assertEqual(cu.match_model(model_id, pricing), model_id)
        usd = cu.price_tokens(
            {"input": 1_000_000, "cache_read": 0, "output": 1_000_000}, model_id, pricing
        )
        self.assertIsInstance(usd, float)
        self.assertGreater(usd, 0.0)


# ---- 10. build_usage_payload: one unified payload feeds the three --json branch shapes -----


class BuildUsagePayloadTests(unittest.TestCase):
    """`build_usage_payload` is the one-scan-pass seam T5 will consume. Each test asserts the
    required unified keys (`branch`, `found`, `priced`, `labels`) AND value-equality between
    the payload and the corresponding printed `--json` dict for every key the two shapes
    share -- proving the CLI's JSON output is genuinely derived from the same payload, not a
    parallel computation that happens to agree today.
    """

    def _printed_json(self, home, extra_args=None):
        args = ["--codex-home", str(home), "--json"] + (extra_args or [])
        with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cu.main(args)
        return json.loads(buf.getvalue())

    def test_absent_branch(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)  # exists, but holds no codex logs
            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                payload = cu.build_usage_payload(home, days=2, top=5)
            printed = self._printed_json(home, ["--days", "2", "--top", "5"])

        self.assertEqual(payload["branch"], "absent")
        self.assertIs(payload["found"], False)
        self.assertIs(payload["priced"], False)
        self.assertEqual(payload["schema_version"], 1)
        self.assertIn(f"codex home absent: {home}", payload["labels"])

        self.assertEqual(printed["branch"], "absent")
        for key in ("branch", "codex_home", "message"):
            self.assertEqual(payload[key], printed[key], key)

    def test_activity_only_branch(self):
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / "history.jsonl").write_text(
                json.dumps({"session_id": "s1", "ts": int(now.timestamp()), "text": "x"}) + "\n"
            )
            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                payload = cu.build_usage_payload(home, days=2, top=5)
            printed = self._printed_json(home, ["--days", "2", "--top", "5"])

        self.assertEqual(payload["branch"], "activity_only")
        self.assertIs(payload["found"], True)
        self.assertIs(payload["priced"], False)
        self.assertEqual(payload["schema_version"], 1)
        self.assertIn("activity counted, unpriced", payload["labels"])

        self.assertEqual(printed["branch"], "activity_only")
        for key in ("branch", "days", "codex_home", "note", "sessions", "records",
                    "malformed_lines", "models_seen", "read_errors"):
            self.assertEqual(payload[key], printed[key], key)

    def test_priced_branch(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            _write_rollout(
                home,
                [_model_rec("fake-mid"),
                 _tok_rec("total_token_usage", input_tokens=100000, cached_input_tokens=50000,
                          output_tokens=20000)],
                name="rollout-priced.jsonl",
            )
            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                payload = cu.build_usage_payload(home, days=2, top=5)
            printed = self._printed_json(home, ["--days", "2", "--top", "5"])

        self.assertEqual(payload["branch"], "priced")
        self.assertIs(payload["found"], True)
        self.assertIs(payload["priced"], True)
        self.assertEqual(payload["schema_version"], 1)
        self.assertIn(
            "API-price estimate from found tokens (est.) — never a bill", payload["labels"]
        )

        self.assertEqual(printed["branch"], "priced")
        for key in ("branch", "days", "codex_home", "disclaimer", "total_usd",
                    "rollouts_scanned", "rollouts_with_tokens", "by_model", "top_rollouts",
                    "unpriced_models", "malformed_lines", "read_errors", "cached_date"):
            self.assertEqual(payload[key], printed[key], key)

    def test_builder_never_prints(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            _write_rollout(
                home,
                [_model_rec("fake-mid"),
                 _tok_rec("total_token_usage", input_tokens=1000, output_tokens=100)],
            )
            buf = io.StringIO()
            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                with contextlib.redirect_stdout(buf):
                    payload = cu.build_usage_payload(home, days=2, top=5)
        self.assertEqual(buf.getvalue(), "")
        self.assertEqual(payload["branch"], "priced")


# ---- 11. the public payload is bounded; ALL render transport lives under _render -----------


class PublicPayloadIsBoundedTests(unittest.TestCase):
    """T4b/F4: the priced payload used to carry `_pricing` (the entire pricing file),
    `_by_model`, and `_rows_sorted` (EVERY rollout, uncapped) as three separate top-level
    keys -- roughly 89% of the dict was render-only transport a consumer had to know to
    strip. All of it now lives under ONE key, `_render`; the public payload (everything
    else) is card fields only, every list `top`-capped. Bounded-ness is asserted against a
    fixture with far MORE rollouts than `top`, so an uncapped list would be visible."""

    ROLLOUTS = 40
    TOP = 3

    def _home(self, td):
        home = Path(td)
        for i in range(self.ROLLOUTS):
            _write_rollout(
                home,
                [_model_rec("fake-mid"),
                 _tok_rec("total_token_usage", input_tokens=1000 * (i + 1),
                          cached_input_tokens=10 * (i + 1), output_tokens=100 * (i + 1))],
                name=f"rollout-{i:03d}.jsonl",
            )
        return home

    def _payload(self, home, top=None):
        with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
            return cu.build_usage_payload(home, days=2, top=self.TOP if top is None else top)

    def test_render_is_the_only_underscore_key_on_every_branch(self):
        with tempfile.TemporaryDirectory() as td:
            priced = self._payload(self._home(td))
        with tempfile.TemporaryDirectory() as td:
            absent = self._payload(Path(td))
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            (home / "history.jsonl").write_text(json.dumps(
                {"session_id": "s1", "ts": int(datetime.now(timezone.utc).timestamp()),
                 "text": "x"}) + "\n")
            activity = self._payload(home)

        for name, payload in (("priced", priced), ("absent", absent),
                              ("activity_only", activity)):
            with self.subTest(branch=name):
                stray = [k for k in payload if k.startswith("_") and k != "_render"]
                self.assertEqual(stray, [], f"{name}: stray transport keys {stray}")
                self.assertNotIn("_pricing", payload)
                self.assertNotIn("_by_model", payload)
                self.assertNotIn("_rows_sorted", payload)

    def test_public_payload_carries_no_uncapped_per_rollout_list(self):
        with tempfile.TemporaryDirectory() as td:
            payload = self._payload(self._home(td))

        public = {k: v for k, v in payload.items() if k != "_render"}
        json.dumps(public)  # the public card is JSON-serializable on its own

        self.assertEqual(len(payload["top_rollouts"]), self.TOP)
        self.assertEqual(payload["rollouts_scanned"], self.ROLLOUTS)  # all were scanned

        # Every public list is bounded by `top` or by the pricing roster (by_model,
        # unpriced_models are keyed by model), so none can grow with the rollout count.
        ceiling = max(self.TOP, len(FIXTURE["models"]))
        self.assertLess(ceiling, self.ROLLOUTS)  # the check can actually fail
        for key, value in public.items():
            if isinstance(value, list):
                self.assertLessEqual(
                    len(value), ceiling,
                    f"public key {key!r} carries {len(value)} entries with top={self.TOP} "
                    f"-- an uncapped list escaped into the public payload",
                )

        # The public card grows with `top`, not with the rollout count: 40 rollouts must
        # not make it materially bigger than 4 do.
        with tempfile.TemporaryDirectory() as td:
            small = self._payload(self._home_n(td, self.TOP + 1))
        small_public = {k: v for k, v in small.items() if k != "_render"}
        self.assertLessEqual(
            len(json.dumps(public)), len(json.dumps(small_public)) * 2,
            "public payload size scales with the number of rollouts, not with `top`",
        )
        # ...while _render still holds the (capped) transport the markdown needs.
        self.assertEqual(len(payload["_render"]["rows_sorted"]), self.TOP)

    def _home_n(self, td, n):
        home = Path(td)
        for i in range(n):
            _write_rollout(
                home,
                [_model_rec("fake-mid"),
                 _tok_rec("total_token_usage", input_tokens=1000 * (i + 1),
                          cached_input_tokens=10 * (i + 1), output_tokens=100 * (i + 1))],
                name=f"rollout-{i:03d}.jsonl",
            )
        return home

    def test_render_rows_sorted_is_capped_at_top_because_markdown_only_reads_that_slice(self):
        with tempfile.TemporaryDirectory() as td:
            payload = self._payload(self._home(td))
        self.assertEqual(len(payload["_render"]["rows_sorted"]), self.TOP)
        self.assertEqual(sorted(payload["_render"]), ["by_model", "pricing", "rows_sorted"])
        # by_model is keyed by pricing model, so it is bounded by the roster, not rollouts.
        self.assertLessEqual(len(payload["_render"]["by_model"]), len(FIXTURE["models"]))

    def test_markdown_still_renders_from_render_transport(self):
        with tempfile.TemporaryDirectory() as td:
            home = self._home(td)
            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    cu.main(["--codex-home", str(home), "--days", "2",
                             "--top", str(self.TOP)])
            md = buf.getvalue()
        self.assertIn("## Spend by model", md)
        self.assertIn(f"## Top {self.TOP} rollouts by estimated cost", md)
        self.assertIn(FIXTURE["models"]["fake-mid"]["display"], md)
        # Exactly `top` rollout rows in the table (header + separator + TOP rows).
        rollout_rows = [ln for ln in md.splitlines() if ln.startswith("| rollout-")]
        self.assertEqual(len(rollout_rows), self.TOP)


# ---- T10: --kits-dir DATE-level ledger join -------------------------------------------------
#
# The brief's own verbatim label ("ledger join, time-window match") was overridden per
# graph-convergence NOTES.md T10: a `run=` id carries no clock (PLAN D8's four hex characters
# are random), so only a same-day match is derivable. These tests pin the honest label text
# (ported verbatim from test_copilot_usage.py's sibling suite), the date-only join via the
# rollout file's date-partitioned path, the ambiguity-reporting rule (list every candidate,
# never guess one), read-only behavior over `--kits-dir`, and byte-identical degrade when
# unused/unmatched. Only the "priced" branch has rows to annotate (module docstring).


def _kit_notes(run_id, task_ids):
    lines = ["# NOTES\n"]
    for t in task_ids:
        lines.append(
            f"outcome: {t} model=sonnet attempts=1 result=pass review=clean run={run_id}"
        )
    return "\n".join(lines) + "\n"


class LedgerJoinTests(unittest.TestCase):
    WHEN = datetime(2026, 7, 26, 10, 0, 0, tzinfo=timezone.utc)

    def _make_home(self, td):
        home = Path(td) / "codex-home"
        _write_rollout(
            home,
            [
                _model_rec("fake-mid"),
                _tok_rec(
                    "total_token_usage",
                    input_tokens=1000, cached_input_tokens=100, output_tokens=200,
                ),
            ],
            when=self.WHEN, name="rollout-a.jsonl",
        )
        return home

    def test_no_kits_dir_flag_leaves_output_byte_identical(self):
        with tempfile.TemporaryDirectory() as td:
            home = self._make_home(td)
            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                without = cu.build_usage_payload(home, days=30, top=10)
                with_none = cu.build_usage_payload(home, days=30, top=10, kits_dir=None)
        self.assertEqual(without, with_none)
        self.assertNotIn("ledger_join", without["top_rollouts"][0])
        self.assertNotIn("kits_dir", without)

    def test_matching_kits_dir_annotates_rollout_with_honest_label(self):
        with tempfile.TemporaryDirectory() as td:
            home = self._make_home(td)
            kits_dir = Path(td) / "kits"
            kit = kits_dir / "demo-kit"
            kit.mkdir(parents=True)
            run_id = f"{self.WHEN:%Y-%m-%d}-9f3a"
            (kit / "NOTES.md").write_text(_kit_notes(run_id, ["T7", "T8"]))

            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                payload = cu.build_usage_payload(home, days=30, top=10, kits_dir=str(kits_dir))

            row = payload["top_rollouts"][0]
            self.assertIn("ledger_join", row)
            lj = row["ledger_join"]
            self.assertEqual(
                lj["label"],
                "(ledger join, same-day run-id match — not a time-window match)",
            )
            self.assertEqual(lj["label"], cu.LEDGER_JOIN_LABEL)
            self.assertEqual(lj["date"], f"{self.WHEN:%Y-%m-%d}")
            self.assertFalse(lj["ambiguous"])
            self.assertEqual(
                lj["candidates"], [{"kit": "demo-kit", "run": run_id, "tasks": ["T7", "T8"]}]
            )
            self.assertEqual(payload["kits_dir"], str(kits_dir))

            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    cu.main(["--codex-home", str(home), "--kits-dir", str(kits_dir)])
                md = buf.getvalue()
            self.assertIn(cu.LEDGER_JOIN_LABEL, md)
            self.assertIn("## Ledger join (--kits-dir)", md)
            self.assertIn("T7, T8", md)

            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    cu.main(["--codex-home", str(home), "--kits-dir", str(kits_dir), "--json"])
                printed = json.loads(buf.getvalue())
            self.assertEqual(printed["kits_dir"], str(kits_dir))
            self.assertIn("ledger_join", printed["top_rollouts"][0])

    def test_non_matching_date_degrades_to_unannotated_byte_identical_markdown(self):
        with tempfile.TemporaryDirectory() as td:
            home = self._make_home(td)
            kits_dir = Path(td) / "kits"
            kit = kits_dir / "demo-kit"
            kit.mkdir(parents=True)
            other_day = self.WHEN - timedelta(days=9)
            run_id = f"{other_day:%Y-%m-%d}-abcd"
            (kit / "NOTES.md").write_text(_kit_notes(run_id, ["T1"]))

            annotated_attempt = _run_main(home, ["--kits-dir", str(kits_dir)])
            without = _run_main(home)

        self.assertEqual(annotated_attempt, without)
        self.assertNotIn("Ledger join", annotated_attempt)

    def test_absent_kits_dir_path_degrades_silently(self):
        with tempfile.TemporaryDirectory() as td:
            home = self._make_home(td)
            missing = Path(td) / "does-not-exist"
            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                payload = cu.build_usage_payload(home, days=30, top=10, kits_dir=str(missing))
        self.assertNotIn("ledger_join", payload["top_rollouts"][0])
        self.assertNotIn("kits_dir", payload)

    def test_ambiguous_same_date_lists_every_candidate_never_guesses(self):
        with tempfile.TemporaryDirectory() as td:
            home = self._make_home(td)
            kits_dir = Path(td) / "kits"
            kit_a = kits_dir / "kit-alpha"
            kit_b = kits_dir / "kit-beta"
            kit_a.mkdir(parents=True)
            kit_b.mkdir(parents=True)
            run_a = f"{self.WHEN:%Y-%m-%d}-1111"
            run_b = f"{self.WHEN:%Y-%m-%d}-2222"
            (kit_a / "NOTES.md").write_text(_kit_notes(run_a, ["T1"]))
            (kit_b / "NOTES.md").write_text(_kit_notes(run_b, ["T5", "T6"]))

            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                payload = cu.build_usage_payload(home, days=30, top=10, kits_dir=str(kits_dir))

            lj = payload["top_rollouts"][0]["ledger_join"]
            self.assertTrue(lj["ambiguous"])
            self.assertEqual(len(lj["candidates"]), 2)
            self.assertEqual(
                sorted(c["kit"] for c in lj["candidates"]), ["kit-alpha", "kit-beta"]
            )

            md = _run_main(home, ["--kits-dir", str(kits_dir)])
            self.assertIn("matched more than one kit/run on the same date", md)

    def test_kits_dir_never_written_to(self):
        with tempfile.TemporaryDirectory() as td:
            home = self._make_home(td)
            kits_dir = Path(td) / "kits"
            kit = kits_dir / "demo-kit"
            kit.mkdir(parents=True)
            run_id = f"{self.WHEN:%Y-%m-%d}-9f3a"
            (kit / "NOTES.md").write_text(_kit_notes(run_id, ["T1"]))

            def snapshot():
                files = sorted(p for p in kits_dir.rglob("*") if p.is_file())
                return [str(p) for p in files], {str(p): p.read_bytes() for p in files}

            before = snapshot()
            with mock.patch.object(cu, "load_pricing", return_value=FIXTURE):
                cu.build_usage_payload(home, days=30, top=10, kits_dir=str(kits_dir))
            after = snapshot()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
