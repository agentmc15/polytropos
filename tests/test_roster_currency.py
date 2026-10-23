"""Roster-currency guard for the Claude Code surfaces.

Derives from ``data/pricing.json`` the CURRENT display name of the ``sonnet`` and
``opus`` tiers (the first row of the tier, the same rule ``bin/claude_execute.py::
resolve_tier`` uses) and every SUPERSEDED one (later rows). Then asserts:

* no ``skills/*/SKILL.md`` (except ``skills/setup/SKILL.md``, whose example
  statusline JSON is test-pinned) names a superseded display name as a standalone
  token, unless the same line says ``superseded`` / ``historical`` / ``retained`` /
  ``older``;
* neither ``.claude-plugin`` manifest description names any display name from any
  tier, so a roster-free description cannot rot.

The haiku and frontier tiers are excluded from the superseded check on purpose:
Haiku 5.5 sits second in its tier without being superseded (it is priced but not
yet the dispatch default; PLAN D2), and "Fable 5" is a protected quotation
(PLAN D8) that appears in the architect skill's slogan.

Live-tree and read-only: nothing is written into the repo. The synthetic negative
in ``SkillRosterCurrencyTests`` proves the checker is not vacuous.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXEMPT_WORDS = ("superseded", "historical", "retained", "older")
GUARDED_TIERS = ("sonnet", "opus")


def _rows(pricing: dict) -> list[dict]:
    """Model rows in file order (``models`` is an id-keyed mapping)."""
    models = pricing["models"]
    return list(models.values()) if isinstance(models, dict) else list(models)


def superseded_names(pricing: dict, tiers=GUARDED_TIERS) -> list[str]:
    """Display names of every non-first row of each guarded tier."""
    out: list[str] = []
    for tier in tiers:
        rows = [m for m in _rows(pricing) if m.get("tier") == tier]
        out.extend(m["display"] for m in rows[1:])
    return out


def standalone_pattern(name: str) -> re.Pattern:
    # "Sonnet 5" must not match "Sonnet 5.5" or "Sonnet 50".
    return re.compile(re.escape(name) + r"\b(?![.\d])")


def stale_lines(text: str, names: list[str]) -> list[str]:
    """Lines naming a superseded display name without an exemption word."""
    pats = [standalone_pattern(n) for n in names]
    hits = []
    for line in text.splitlines():
        low = line.lower()
        if any(w in low for w in EXEMPT_WORDS):
            continue
        if any(p.search(line) for p in pats):
            hits.append(line.strip())
    return hits


def assert_no_stale(text: str, names: list[str], label: str) -> None:
    hits = stale_lines(text, names)
    if hits:
        raise AssertionError(f"{label} names a superseded roster entry: {hits}")


def _pricing() -> dict:
    return json.loads((ROOT / "data" / "pricing.json").read_text(encoding="utf-8"))


class SkillRosterCurrencyTests(unittest.TestCase):
    def test_derivation_finds_superseded_names(self):
        names = superseded_names(_pricing())
        self.assertTrue(names, "pricing.json must carry superseded sonnet/opus rows")

    def test_no_skill_names_a_superseded_default_as_current(self):
        names = superseded_names(_pricing())
        skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
        self.assertTrue(skills)
        for path in skills:
            if path.parent.name == "setup":
                continue
            assert_no_stale(path.read_text(encoding="utf-8"), names,
                            str(path.relative_to(ROOT)))

    def test_same_checker_fails_on_a_synthetic_stale_string(self):
        fake = {"models": {
            "a": {"tier": "sonnet", "display": "Sonnet 5.5"},
            "b": {"tier": "sonnet", "display": "Sonnet 5"},
        }}
        names = superseded_names(fake)
        self.assertEqual(names, ["Sonnet 5"])
        with self.assertRaises(AssertionError):
            assert_no_stale("use Sonnet 5 for edits", names, "synthetic")
        # The current name and an exempted historical mention both pass.
        assert_no_stale("use Sonnet 5.5 for edits", names, "synthetic")
        assert_no_stale("Sonnet 5 is a superseded row", names, "synthetic")


class ManifestDescriptionTests(unittest.TestCase):
    def test_manifest_descriptions_name_no_model(self):
        names = [m["display"] for m in _rows(_pricing())]
        for fname in ("plugin.json", "marketplace.json"):
            data = json.loads((ROOT / ".claude-plugin" / fname).read_text(encoding="utf-8"))
            descs = []

            def walk(o):
                if isinstance(o, dict):
                    for k, v in o.items():
                        if k == "description" and isinstance(v, str):
                            descs.append(v)
                        else:
                            walk(v)
                elif isinstance(o, list):
                    for v in o:
                        walk(v)
            walk(data)
            self.assertTrue(descs, f"{fname} has no description")
            for d in descs:
                for n in names:
                    self.assertFalse(standalone_pattern(n).search(d),
                                     f"{fname} description names {n!r}: {d}")


if __name__ == "__main__":
    unittest.main()
