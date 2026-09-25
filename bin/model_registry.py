#!/usr/bin/env python3
"""The model registry: which harness knows a model id, and what tier it sits in there.

WHAT WAS WRONG. `routing_scorecard.tier_for` was identity except `fable -> frontier`, so a
ledger line whose `model=` named a concrete id (`claude-opus-5`, `gpt-6-astra`) resolved to a
"tier" nobody's ladder contains and was skipped with a note. A valid Astra pass contributed
zero tier outcomes. `bench_routing` had its own Claude-only join by normalized id. Each was a
private answer to the same question.

WHAT THIS IS. One READ-ONLY reader over the three pricing files -- `data/pricing.json`,
`data/pricing.codex.json`, `data/pricing.copilot.json` -- that answers "which harness, which
tier" for an alias word or a concrete id, and says which file version it answered from. It
reads model ids and tiers ONLY. It also indexes Copilot's `retired_models` solely so an
evidence reader can classify an old ledger line; each such candidate/result is marked
`retired`. It never reads a price, never merges the files, and never hands one harness's
roster to another harness's driver; the drivers keep resolving through their own file exactly
as before. This exists for the cross-harness evidence readers (the scorecard, the attempt
history, telemetry), which have to name a tier for whatever id a ledger happens to carry.

WHAT IT REFUSES TO GUESS. Tier vocabularies differ per harness (Claude: haiku/sonnet/opus/
frontier; Codex and Copilot: cheap/mid/strong/frontier) and one id can sit in two files with
two tiers (`claude-opus-5` is `opus` to Claude and `strong` to Copilot). So `resolve` takes a
harness when the caller knows one, and without one reports the ambiguity rather than picking:
a tier is returned only when every candidate agrees on it. Unknown ids resolve to None.
"""

import json
from pathlib import Path

REGISTRY_VERSION = "polytropos.model-registry/1"

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

#: Harness -> its pricing file. The three never merge; this maps names to files and no more.
PRICING_FILES = {
    "claude": "pricing.json",
    "codex": "pricing.codex.json",
    "copilot": "pricing.copilot.json",
}
HARNESSES = tuple(PRICING_FILES)

#: Alias words a Claude kit may pin that are not themselves tier words. `fable` is the one
#: the scorecard has always translated; kept here so there is one place that knows it.
CLAUDE_ALIASES = {"fable": "frontier"}


def normalize_id(model_id):
    """Fold a model id to one comparable shape: lowercase, dots -> dashes.

    Benchmark and Claude ids use dashes (`claude-opus-4-8`); `pricing.copilot.json` uses dots
    (`claude-opus-4.8`). Folding both sides makes the join correct whichever side used which.
    """
    return (model_id or "").strip().lower().replace(".", "-")


def _read_pricing(data_dir, harness):
    path = Path(data_dir) / PRICING_FILES[harness]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


class Registry:
    """Model ids and tiers across the harnesses, from the pricing files or an injected bundle.

    `pricing_bundle` (`{harness: pricing_dict}`) is the test seam and `bench_routing`'s: a
    caller that already holds a pricing dict passes it rather than having this read a file.
    """

    def __init__(self, data_dir=None, pricing_bundle=None):
        self.sources = {}
        self.tiers = {}
        self.models = {}
        bundle = dict(pricing_bundle or {})
        if pricing_bundle is None:
            for harness in HARNESSES:
                bundle[harness] = _read_pricing(data_dir or DATA_DIR, harness)
        for harness, pricing in bundle.items():
            if not isinstance(pricing, dict):
                self.sources[harness] = {"file": PRICING_FILES.get(harness), "cached_date": None,
                                         "loaded": False}
                self.tiers[harness] = []
                continue
            self.sources[harness] = {"file": PRICING_FILES.get(harness),
                                     "cached_date": pricing.get("cached_date"), "loaded": True}
            tiers = []
            for model_id, info in (pricing.get("models") or {}).items():
                if not isinstance(info, dict):
                    continue
                tier = info.get("tier")
                if tier and tier not in tiers:
                    tiers.append(tier)
                self.models.setdefault(normalize_id(model_id), []).append({
                    "harness": harness,
                    "id": model_id,
                    "tier": tier,
                    "vendor": info.get("vendor"),
                    "retired": False,
                })
            # Copilot preserves retired entries for historical pricing. They are evidence-only:
            # indexing them here lets old attempt records retain their original Copilot tier,
            # but they never enter `tiers`, which is the registry's active selectable vocabulary.
            # Other harnesses currently have no retired map; accepting it generically keeps the
            # reader schema-oriented without granting any dispatcher a new selection path.
            for model_id, info in (pricing.get("retired_models") or {}).items():
                if not isinstance(info, dict):
                    continue
                self.models.setdefault(normalize_id(model_id), []).append({
                    "harness": harness,
                    "id": model_id,
                    "tier": info.get("tier"),
                    "vendor": info.get("vendor"),
                    "retired": True,
                })
            self.tiers[harness] = tiers

    def versions(self):
        """`{harness: cached_date}` -- the registry version a decision was made against."""
        return {h: s.get("cached_date") for h, s in self.sources.items()}

    def _candidates(self, model, harness):
        text = "" if model is None else str(model).strip()
        if not text:
            return []
        found = []
        harnesses = [harness] if harness else list(self.sources)
        for h in harnesses:
            if text in self.tiers.get(h, ()):
                found.append({"harness": h, "id": None, "tier": text, "kind": "tier-word"})
            elif h == "claude" and text in CLAUDE_ALIASES:
                found.append({"harness": h, "id": None, "tier": CLAUDE_ALIASES[text],
                              "kind": "alias"})
        for entry in self.models.get(normalize_id(text), []):
            if harness is None or entry["harness"] == harness:
                found.append({"harness": entry["harness"], "id": entry["id"],
                              "tier": entry["tier"], "kind": "model",
                              "vendor": entry.get("vendor"),
                              # Keep `kind=model` for readers that predate retired entries;
                              # this additive marker tells evidence consumers it is historical.
                              "retired": bool(entry.get("retired"))})
        return found

    def resolve(self, model, harness=None):
        """What `model` is -> a dict, or None when no harness knows it.

        With `harness`, the answer is that harness's alone. Without it, the answer names the
        harness only when exactly one has an opinion, and names a tier only when every
        candidate agrees; otherwise `harness` is None, `ambiguous` lists the harnesses, and
        `tier` is None. A caller that needs certainty passes the harness it knows.
        """
        found = self._candidates(model, harness)
        if not found:
            return None
        harnesses = []
        for entry in found:
            if entry["harness"] not in harnesses:
                harnesses.append(entry["harness"])
        tiers = {entry["tier"] for entry in found}
        first = found[0]
        result = {
            "query": model,
            "harness": harnesses[0] if len(harnesses) == 1 else None,
            "ambiguous": harnesses if len(harnesses) > 1 else [],
            "tier": first["tier"] if len(tiers) == 1 else None,
            "tiers": {entry["harness"]: entry["tier"] for entry in found},
            "id": first.get("id"),
            "kind": first["kind"],
            "retired": bool(first.get("retired")),
            "registry": {h: self.sources.get(h, {}).get("cached_date") for h in harnesses},
        }
        return result

    def tier_of(self, model, harness=None):
        """The tier alone, or None -- never a guess between harnesses that disagree."""
        hit = self.resolve(model, harness=harness)
        return hit["tier"] if hit else None

    def harness_of(self, model):
        """The one harness that knows `model`, or None when none or several do."""
        hit = self.resolve(model)
        return hit["harness"] if hit else None


_DEFAULT = None


def registry(data_dir=None):
    """The registry over the repo's own pricing files, loaded once per process."""
    global _DEFAULT
    if data_dir is not None:
        return Registry(data_dir=data_dir)
    if _DEFAULT is None:
        _DEFAULT = Registry()
    return _DEFAULT


def _cli(argv=None):
    import argparse
    import sys
    ap = argparse.ArgumentParser(
        prog="model_registry.py",
        description="Which harness knows a model id, and what tier it sits in there. Reads "
                    "ids and tiers from the three pricing files; never a price.",
    )
    ap.add_argument("model", nargs="?", help="alias word or concrete id to resolve")
    ap.add_argument("--harness", choices=HARNESSES, default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    reg = registry()
    if not args.model:
        payload = {"version": REGISTRY_VERSION, "sources": reg.sources, "tiers": reg.tiers,
                   "models": len(reg.models)}
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    hit = reg.resolve(args.model, harness=args.harness)
    if args.json:
        print(json.dumps(hit, indent=2, sort_keys=True))
    elif hit is None:
        print(f"{args.model}: unknown to every pricing file")
    else:
        where = hit["harness"] or f"ambiguous ({', '.join(hit['ambiguous'])})"
        print(f"{args.model}: harness={where} tier={hit['tier'] or 'disagrees'} "
              f"tiers={hit['tiers']} registry={hit['registry']}")
    return 0 if hit or not args.model else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
