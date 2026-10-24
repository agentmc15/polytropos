"""Hidden oracle for T2 (`copilot_pricing.py est` with a model list). Never shown to a candidate.

Expected figures are recomputed here from the sandbox's own `data/pricing.copilot.json` with
the base commit's formula, so no price or model id is written into this file.
"""

import contextlib
import importlib.util
import io
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRICING = json.loads((ROOT / "data" / "pricing.copilot.json").read_text(encoding="utf-8"))


def _load():
    spec = importlib.util.spec_from_file_location("route_oracle_copilot_pricing",
                                                  ROOT / "bin" / "copilot_pricing.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cp = _load()


def call(*argv):
    """(exit code, stdout, stderr) of `copilot_pricing.main(argv)`."""
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            cp.main(list(argv))
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    return code, out.getvalue(), err.getvalue()


def expected(profile, model_id, cache_hit=0.8):
    """The base commit's est formula, recomputed independently of the candidate."""
    p = PRICING["task_profiles"][profile]
    model = PRICING["models"][model_id]
    rates, which = model, "base"
    lc = model.get("long_context")
    if lc and p["input_tokens"] > lc["threshold_tokens"]:
        rates, which = lc, "long_context"
    usd = (p["input_tokens"] * ((1 - cache_hit) * rates["input_per_mtok"]
                                + cache_hit * rates["cached_input_per_mtok"]) / 1e6
           + p["output_tokens"] / 1e6 * rates["output_per_mtok"])
    return usd, usd / PRICING["billing_unit"]["usd_per_credit"], which


def ids(n):
    return list(PRICING["models"])[:n]


class SingleIdUnchanged(unittest.TestCase):
    def test_text_block(self):
        model = ids(1)[0]
        usd, aic, which = expected("M", model)
        code, out, err = call("est", "M", model)
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith(
            f"profile M on {model}, cache_hit=0.8\n  usd:   ${usd:.4f}\n  aic:   {aic:.1f}\n"
            f"  rates: {which}\n"), out)
        self.assertNotIn("cheapest", out)

    def test_json_is_an_object(self):
        model = ids(1)[0]
        code, out, _ = call("est", "S", model, "--json")
        self.assertEqual(code, 0)
        obj = json.loads(out)
        self.assertIsInstance(obj, dict)
        self.assertEqual(obj["model_id"], model)
        self.assertEqual(set(obj), {"profile", "model_id", "cache_hit", "usd", "aic",
                                    "rates_used", "warnings"})

    def test_unknown_single_id_exits_2(self):
        code, out, err = call("est", "M", "no-such-model")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("no-such-model", err)


class ListForm(unittest.TestCase):
    def test_text_blocks_in_order_with_blank_separator_and_cheapest(self):
        models = ids(3)
        code, out, err = call("est", "M", ",".join(models))
        self.assertEqual(code, 0, err)
        blocks = out.rstrip("\n").split("\n\n")
        self.assertEqual(len(blocks), 3, out)
        aics = []
        for block, model in zip(blocks, models):
            usd, aic, which = expected("M", model)
            aics.append((aic, model))
            self.assertTrue(block.startswith(f"profile M on {model}, cache_hit=0.8\n"), block)
            self.assertIn(f"  usd:   ${usd:.4f}\n", block)
            self.assertIn(f"  aic:   {aic:.1f}\n", block)
        lines = out.rstrip("\n").splitlines()
        best = min(aics, key=lambda pair: pair[0])
        self.assertEqual(lines[-1], f"cheapest: {best[1]} ({best[0]:.1f} AIC)")
        self.assertEqual(sum(1 for line in lines if line.startswith("cheapest:")), 1)

    def test_whitespace_around_ids_is_ignored(self):
        models = ids(2)
        a = call("est", "S", ",".join(models))
        b = call("est", "S", " , ".join(models))
        self.assertEqual(a, b)

    def test_json_is_list_in_order(self):
        models = ids(3)
        code, out, _ = call("est", "L", ",".join(models), "--json", "--cache-hit", "0.5")
        self.assertEqual(code, 0)
        rows = json.loads(out)
        self.assertIsInstance(rows, list)
        self.assertEqual([r["model_id"] for r in rows], models)
        for row, model in zip(rows, models):
            usd, aic, which = expected("L", model, cache_hit=0.5)
            self.assertEqual(row["cache_hit"], 0.5)
            self.assertEqual(row["profile"], "L")
            self.assertAlmostEqual(row["usd"], round(usd, 4), places=4)
            self.assertAlmostEqual(row["aic"], round(aic, 4), places=4)
            self.assertEqual(row["rates_used"], which)

    def test_json_rows_match_single_id_json(self):
        models = ids(2)
        _, out, _ = call("est", "M", ",".join(models), "--json")
        rows = json.loads(out)
        for row, model in zip(rows, models):
            _, single, _ = call("est", "M", model, "--json")
            self.assertEqual(row, json.loads(single))

    def test_tie_goes_to_first_listed(self):
        model = ids(1)[0]
        clone = dict(PRICING["models"][model])
        original_load = cp.load_pricing

        def patched():
            data = original_load()
            data["models"]["zz-oracle-clone"] = dict(clone)
            return data

        cp.load_pricing = patched
        try:
            code, out, err = call("est", "M", f"zz-oracle-clone,{model}")
        finally:
            cp.load_pricing = original_load
        self.assertEqual(code, 0, err)
        self.assertTrue(out.rstrip("\n").splitlines()[-1].startswith("cheapest: zz-oracle-clone "))


class ListErrors(unittest.TestCase):
    def assert_refused(self, *argv):
        code, out, err = call(*argv)
        self.assertEqual(code, 2, (argv, out, err))
        self.assertEqual(out, "", argv)
        self.assertTrue(err.strip(), argv)
        return err

    def test_every_unknown_id_is_named(self):
        good = ids(1)[0]
        err = self.assert_refused("est", "M", f"{good},nope-one,nope-two")
        self.assertIn("nope-one", err)
        self.assertIn("nope-two", err)

    def test_empty_segments_refused(self):
        good = ids(2)
        self.assert_refused("est", "M", f"{good[0]},,{good[1]}")
        self.assert_refused("est", "M", f"{good[0]},")

    def test_duplicates_refused(self):
        good = ids(1)[0]
        self.assert_refused("est", "M", f"{good},{good}")

    def test_unknown_profile_with_list(self):
        self.assert_refused("est", "NOPE", ",".join(ids(2)))

    def test_help_mentions_list_form(self):
        help_text = cp.build_parser()._subparsers._group_actions[0].choices["est"].format_help()
        self.assertTrue("comma" in help_text.lower() or "list" in help_text.lower(), help_text)


if __name__ == "__main__":
    unittest.main()
