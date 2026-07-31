#!/usr/bin/env python3
"""Single home for Copilot-side user model preferences (prefs): pins and excludes.

A **pin** resolves WHICH model a tier means — `frontier=<id>` makes `<id>` the frontier
pick everywhere a driver resolves the `frontier` tier. An **exclude** removes a model from
consideration entirely — it is skipped by the escalation ladder and by tier resolution.
Prefs never change WHEN a tier is used (no force-frontier switch, no tier-promotion knob) —
only which model id a tier slot resolves to.

The prefs file is `prefs/copilot.json` at the repo root: gitignored USER DATA, never
committed, never auto-created by any engine, no sample file shipped. Per-run CLI flags
(`--pin`, `--exclude`, `--prefs`, `--no-prefs`) always override the file — see
`effective_prefs` for the precedence rules.

This module is stdlib-only, importable, and carries NO CLI (no `main`), spawns no child
processes, and performs no lookup of the real user home directory. It is the ONLY home for
prefs logic: both `bin/copilot_execute.py` and `bin/copilot_pricing.py` load it lazily via
the house importlib pattern (by absolute path computed from their own `Path(__file__)`) —
the logic is never duplicated in either engine.
"""

import json
from pathlib import Path

TIER_ORDER = ("cheap", "mid", "strong", "frontier")
PREFS_SCHEMA_VERSION = 1

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PREFS_PATH = REPO_ROOT / "prefs" / "copilot.json"


def empty_prefs():
    """The prefs shape with nothing set — the neutral value `effective_prefs` degrades to."""
    return {"pins": {}, "excludes": [], "notes": [], "source": None}


def load_prefs_file(path):
    """Read the raw prefs file at `path`. Returns (pins_dict, excludes_list, notes_list).

    This is a RAW read: entries are structurally sanity-checked (right JSON shapes) but not
    yet validated against a pricing dict — semantic validation (unknown tier, stale model
    id) is `effective_prefs`'s job, since only it has the pricing dict in hand.

    An absent path is normal (no prefs configured yet): empties, no notes. An unreadable
    file, invalid JSON, or a top-level value that isn't a JSON object all degrade to empties
    plus one note (`f"prefs file {path}: malformed ({reason}) — ignoring it"`) — a malformed
    prefs file must never crash a run. Within an otherwise-valid object: `pins` present but
    not a dict of str->str is dropped with a note; `excludes` present but not a list of str
    is dropped with a note. Unknown top-level keys are tolerated silently (forward compat).
    An int `schema_version` greater than `PREFS_SCHEMA_VERSION` earns a best-effort-read
    note but does not otherwise change parsing.
    """
    path = Path(path)
    if not path.exists():
        return {}, [], []

    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        return {}, [], [f"prefs file {path}: malformed ({e}) — ignoring it"]

    if not isinstance(data, dict):
        return {}, [], [
            f"prefs file {path}: malformed (top-level value is not a JSON object) — ignoring it"
        ]

    notes = []
    pins = {}
    excludes = []

    if "pins" in data:
        raw_pins = data["pins"]
        if isinstance(raw_pins, dict) and all(
            isinstance(k, str) and isinstance(v, str) for k, v in raw_pins.items()
        ):
            pins = dict(raw_pins)
        else:
            notes.append(
                f"prefs file {path}: 'pins' must be a dict of tier->model_id strings — dropped"
            )

    if "excludes" in data:
        raw_excludes = data["excludes"]
        if isinstance(raw_excludes, list) and all(isinstance(x, str) for x in raw_excludes):
            excludes = list(raw_excludes)
        else:
            notes.append(
                f"prefs file {path}: 'excludes' must be a list of model_id strings — dropped"
            )

    schema_version = data.get("schema_version")
    if isinstance(schema_version, int) and schema_version > PREFS_SCHEMA_VERSION:
        notes.append(
            f"prefs file {path}: schema_version {schema_version} is newer than "
            f"{PREFS_SCHEMA_VERSION} — best-effort read"
        )

    return pins, excludes, notes


def parse_pin_flag(value, pricing):
    """Parse a `--pin TIER=MODEL_ID` flag value. Returns (tier, model_id).

    Raises `ValueError` on: missing `=` (message shows the required `TIER=MODEL_ID`
    grammar); an unknown tier (message lists `TIER_ORDER`); an unknown model id (message
    mirrors `copilot_pricing.est_cost`'s `valid choices: {sorted(models)}` shape) — these
    are FLAG errors, typed just now, so they are always hard failures.
    """
    if "=" not in value:
        raise ValueError(f"invalid --pin {value!r}: expected TIER=MODEL_ID")
    tier, _, model_id = value.partition("=")
    tier = tier.strip()
    model_id = model_id.strip()

    if tier not in TIER_ORDER:
        raise ValueError(f"unknown tier {tier!r}; valid tiers: {' | '.join(TIER_ORDER)}")

    models = pricing["models"]
    if model_id not in models:
        raise ValueError(f"unknown model id {model_id!r}; valid choices: {sorted(models)}")

    return tier, model_id


def validate_exclude_flag(model_id, pricing):
    """Validate a `--exclude MODEL_ID` flag value. Returns `model_id` unchanged.

    Raises `ValueError` (the same unknown-id message shape as `parse_pin_flag`) when
    `model_id` is not a live key in `pricing["models"]`.
    """
    models = pricing["models"]
    if model_id not in models:
        raise ValueError(f"unknown model id {model_id!r}; valid choices: {sorted(models)}")
    return model_id


def effective_prefs(pricing, prefs_path=None, no_prefs=False, pin_flags=(), exclude_flags=()):
    """The ONE entry point both engines call to compute the active pins/excludes/notes.

    Steps:
      (a) Load file prefs from `Path(prefs_path) if prefs_path else DEFAULT_PREFS_PATH`,
          skipped entirely when `no_prefs` is True (no notes from the file in that case).
      (b) Semantically validate FILE entries against the live `pricing` dict: a pin whose
          tier is not in `TIER_ORDER`, or whose id is not a live pricing key, or an exclude
          id that is not a live key, is SKIPPED with a note naming the entry — roster drift
          in a stored file never bricks a run.
      (c) Flag pins are parsed via `parse_pin_flag` (hard errors propagate) and merged
          PER-TIER over the file pins — a flag pin replaces only its own tier's file pin;
          other file pins survive. Flag excludes are validated via `validate_exclude_flag`;
          the effective excludes are the union of file-then-flag excludes, deduped,
          order-preserving.
      (d) AFTER the merge: any effective pin whose id is also in the effective excludes is a
          hard conflict, from any source combination —
          `ValueError(f"pin {tier}={model_id} conflicts with exclude {model_id} — drop one,
          or use --no-prefs to bypass the prefs file")`.
      (e) For each effective pin whose id's own tier differs from the slot tier, append a
          note naming both tiers (a deliberate, legal cross-tier override — never an error).

    Returns `{"pins", "excludes", "notes", "source"}`; `source` is `str(path)` when
    `no_prefs` is False and the file exists, else `None`.
    """
    models = pricing["models"]
    path = Path(prefs_path) if prefs_path else DEFAULT_PREFS_PATH

    notes = []
    file_pins = {}
    file_excludes = []
    source = None

    if not no_prefs:
        raw_pins, raw_excludes, file_notes = load_prefs_file(path)
        notes.extend(file_notes)
        if path.exists():
            source = str(path)

        for tier, model_id in raw_pins.items():
            if tier not in TIER_ORDER:
                notes.append(
                    f"prefs file {path}: pin {tier}={model_id} has an unknown tier — skipped"
                )
                continue
            if model_id not in models:
                notes.append(
                    f"prefs file {path}: pin {tier}={model_id} is not a live pricing id — skipped"
                )
                continue
            file_pins[tier] = model_id

        for model_id in raw_excludes:
            if model_id not in models:
                notes.append(
                    f"prefs file {path}: exclude {model_id} is not a live pricing id — skipped"
                )
                continue
            file_excludes.append(model_id)

    # (c) flag pins merge per-tier over file pins.
    pins = dict(file_pins)
    for flag in pin_flags:
        tier, model_id = parse_pin_flag(flag, pricing)
        pins[tier] = model_id

    # excludes = file-then-flags union, deduped, order-preserving.
    excludes = []
    for model_id in file_excludes:
        if model_id not in excludes:
            excludes.append(model_id)
    for flag in exclude_flags:
        model_id = validate_exclude_flag(flag, pricing)
        if model_id not in excludes:
            excludes.append(model_id)

    # (d) conflict check, after the merge, from any source combination.
    for tier, model_id in pins.items():
        if model_id in excludes:
            raise ValueError(
                f"pin {tier}={model_id} conflicts with exclude {model_id} — drop one, or "
                "use --no-prefs to bypass the prefs file"
            )

    # (e) cross-tier notes.
    for tier, model_id in pins.items():
        own_tier = models.get(model_id, {}).get("tier")
        if own_tier is not None and own_tier != tier:
            notes.append(
                f"pin {tier}={model_id} is a cross-tier override (model's own tier: {own_tier})"
            )

    return {"pins": pins, "excludes": excludes, "notes": notes, "source": source}


def resolve_tier(pricing, tier, prefs=None):
    """Resolve one tier to a model id, honoring `prefs`.

    Returns the pinned id when `prefs` carries a pin for `tier` (no file-order scan); else
    the first model id in `pricing["models"]` file order whose tier matches `tier` and which
    is not in `prefs`'s excludes; else `None` (tier empty or fully excluded). Raises
    `ValueError` (the same unknown-tier message as `parse_pin_flag`) when `tier` is not in
    `TIER_ORDER`. `prefs=None` behaves exactly like `empty_prefs()`.
    """
    if tier not in TIER_ORDER:
        raise ValueError(f"unknown tier {tier!r}; valid tiers: {' | '.join(TIER_ORDER)}")

    if prefs is None:
        prefs = empty_prefs()

    pins = prefs.get("pins") or {}
    if tier in pins:
        return pins[tier]

    excludes = set(prefs.get("excludes") or [])
    models = pricing["models"]
    for model_id, info in models.items():
        if info.get("tier") == tier and model_id not in excludes:
            return model_id
    return None


def is_empty(prefs):
    """True when `prefs` carries no pins and no excludes (notes/source don't count)."""
    return not prefs["pins"] and not prefs["excludes"]
