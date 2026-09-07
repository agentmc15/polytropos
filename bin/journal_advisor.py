#!/usr/bin/env python3
"""Advisory harness-routing signal builder for the daily journal (PLAN.md D5).

Pure and deterministic: this module turns the digest's per-source adapter reports plus
the three (already-loaded) pricing dicts into a ``signals.harness`` block that the
summarizer's next-day prompt reads to recommend, per next-day task, a harness (Claude
Code / Copilot CLI / Codex CLI), a model tier, a ready-to-paste command, and a one-line
WHY. It preserves the journal's deterministic-signals-then-prose split (daily-journal
D10): this file produces only structured signals; the model writes the prose.

ADVISORY ONLY. Nothing here dispatches, executes, schedules, or auto-pins anything — the
user reads the recommendation and decides. The module never spawns a process, never opens
a network connection (the journal is offline by contract), and never reads a home
directory or a ``data/`` file: every pricing dict arrives as an argument, and the two
reused estimators are imported read-only via the ``bin/session_cost.py`` importlib
pattern.

Reuse map (read-only, never edited, never re-implemented):
  * Copilot estimates -> ``copilot_pricing.est_cost`` (USD + AIC, priced from
    ``data/pricing.copilot.json``).
  * Codex estimates   -> ``codex_pricing.resolve_tier`` + ``codex_pricing.est_cost`` (the
    tier skip-up rule and the dual-framed API-equivalent estimate).
The Claude side has no estimator script to reuse, so the advisor computes the SAME
documented formula shape from the ``data/pricing.json`` values passed in
(input x ((1-h)*rate_in + h*rate_in*cache_read_multiplier)/1e6 + output/1e6 * rate_out) —
documented parity with the two sibling estimators, no new hardcoded rate or literal.

Not-a-bill Codex framing (PLAN.md D3, absolute): the three pricing files never merge and
no harness's rates are ever applied to another harness's model. A Codex dollar figure is
never a bill — codex estimate entries carry ``usd_api_equivalent`` (never a plain "cost")
alongside ``billed_usd: None``, and the ``codex_cli`` ``usd_today`` is always None (a
subscription run is usage-limited, not token-billed; the digest's relative-burn proxy is
surfaced as ``proxy_today``). Codex model ids are best-effort data resolved from the
pricing dict at run time — never written as a literal here.

Honesty: absent data is ``None`` plus an aggregate note — never a fabricated number and
never a zero standing in for an unknown. A missing report -> ``available_today: False``; a
``None`` pricing dict -> ``est: None`` + a note; an unpopulated tier or unknown profile ->
a ``None`` slot + a note.
"""

import importlib.util
import shlex
from pathlib import Path


def _load(name):
    """Load a sibling ``bin/<name>.py`` module read-only (the session_cost.py pattern)."""
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parent / f"{name}.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cp = _load("copilot_pricing")   # Copilot-side USD + AIC estimator (read-only reuse)
cxp = _load("codex_pricing")    # Codex-side tier resolver + dual-framed estimator (read-only reuse)


# ---- pinned constants ------------------------------------------------------------------------

# Two comparable task sizes to estimate per harness (task-profile keys, not model ids).
ADVISOR_PROFILES = ("S", "M")
# Default cache-hit ratio — matches the reused estimators' own defaults.
ADVISOR_CACHE_HIT = 0.8

ADVISORY_NOTE = (
    "Advisory only — deterministic routing signals for a human decision; "
    "nothing here auto-executes."
)

# Repo-pinned dispatch shapes (journal_summarize.build_dispatch; CLAUDE.md's `copilot -p`
# invariant + copilot_execute's `--model` flag; codex_execute.build_dispatch). The advisor
# NEVER invents a CLI flag.
#
# These are ARGV, not shell strings. They used to be format strings with the task interpolated
# inside double quotes -- where `$(...)` is still evaluated, so a card title carrying command
# substitution became a live command the moment a human pasted the line. Deleting `"` and
# backticks from the title did not close that, because `$(...)` needs neither.
#
# Each slot below is a WHOLE element, and substitution is by exact element equality: a task
# whose text is literally "{{task}}" fills its own slot and nothing else. Task text is never
# parsed, escaped, or edited on the way in -- only quoted on the way out, by the renderer.
MODEL_SLOT = "{{model}}"
TASK_SLOT = "{{task}}"

COMMAND_ARGV = {
    "claude_code": ("claude", "-p", "--model", MODEL_SLOT, TASK_SLOT),
    "copilot_cli": ("copilot", "--model", MODEL_SLOT, "-p", TASK_SLOT),
    "codex_cli": (
        "codex", "exec", "--model", MODEL_SLOT, "--sandbox", "workspace-write", TASK_SLOT
    ),
}

#: The one display renderer implemented here. `shlex.join` serializes for POSIX shells
#: (sh/bash/zsh). PowerShell and cmd.exe are deliberately NOT implemented: their quoting rules
#: differ, and POSIX quoting applied to either is wrong in ways that silently re-enable the
#: bug this exists to fix. An unimplemented shell gets no renderer rather than a plausible one.
DISPLAY_SHELL = "posix"


def build_command_argv(harness, model, task):
    """The literal argv for one advisory dispatch on `harness`.

    `task` is placed as one argv element, byte for byte -- quotes, `$(...)`, backticks,
    newlines, backslashes and all. Raises KeyError for a harness with no pinned shape, which
    is the point: the shape comes from this table, never from a caller or a digest.
    """
    spec = COMMAND_ARGV.get(harness)
    if spec is None:
        raise KeyError(f"no pinned dispatch shape for harness {harness!r}")
    argv = []
    for element in spec:
        if element == MODEL_SLOT:
            argv.append(str(model))
        elif element == TASK_SLOT:
            argv.append(task if isinstance(task, str) else str(task))
        else:
            argv.append(element)
    return argv


def render_command(harness, model, task):
    """A ready-to-paste POSIX shell line for `harness`, with `task` preserved literally.

    ADVISORY: this renders text for a human to read and decide about. Nothing here executes
    it, and nothing should start to -- the safety of the rendering is what makes it safe to
    display, not a substitute for the human in front of it.
    """
    return shlex.join(build_command_argv(harness, model, task))

# Per-harness structural billing strings (label semantics — no numbers).
BILLING = {
    "claude_code": "priced from data/pricing.json (subscription or API)",
    "copilot_cli": "AIC credits — priced from data/pricing.copilot.json",
    "codex_cli": (
        "subscription usage-limited; dollars are API-equivalent relative-burn proxies "
        "from data/pricing.codex.json — never a bill"
    ),
}

# The advisor's two estimate slots ("cheap", "mid") mapped onto each pricing file's tier
# vocabulary. Claude uses data/pricing.json's haiku/sonnet words; Copilot and Codex use
# their own shared cheap/mid words.
CLAUDE_TIER_SLOTS = (("cheap", "haiku"), ("mid", "sonnet"))
COPILOT_TIER_SLOTS = (("cheap", "cheap"), ("mid", "mid"))
CODEX_TIER_SLOTS = (("cheap", "cheap"), ("mid", "mid"))


# ---- helpers ---------------------------------------------------------------------------------

def _note(notes, msg):
    """Append an aggregate note once (dedup identical strings)."""
    if msg not in notes:
        notes.append(msg)


def _first_model_of_tier(models, tier_word):
    """First model id in file order whose ``tier`` equals ``tier_word`` (or None)."""
    for model_id, spec in models.items():
        if isinstance(spec, dict) and spec.get("tier") == tier_word:
            return model_id
    return None


def _claude_est(pricing, profiles, cache_hit, notes):
    """Claude-side estimates. No claude-side estimator script exists to reuse, so this
    computes the documented formula-parity shape straight from ``data/pricing.json`` values
    passed in — never a new hardcoded rate."""
    if pricing is None:
        _note(notes, "claude_code: pricing unavailable — no estimates")
        return None
    models = pricing.get("models", {})
    task_profiles = pricing.get("task_profiles", {})
    cache_read_mult = pricing.get("cache_read_multiplier")

    # Resolve each slot's representative model ONCE (model choice is profile-independent).
    slot_models = {}
    for slot_name, tier_word in CLAUDE_TIER_SLOTS:
        model_id = _first_model_of_tier(models, tier_word)
        slot_models[slot_name] = model_id
        if model_id is None:
            _note(notes, f"claude_code: no {tier_word}-tier model in pricing.json — "
                         f"{slot_name} slot has no estimate")

    if cache_read_mult is None:
        _note(notes, "claude_code: cache_read_multiplier missing from pricing.json — "
                     "no estimates")

    est = {}
    for profile in profiles:
        p = task_profiles.get(profile)
        slots = {}
        for slot_name, _tier_word in CLAUDE_TIER_SLOTS:
            model_id = slot_models[slot_name]
            if model_id is None or cache_read_mult is None or p is None:
                slots[slot_name] = None
                if model_id is not None and cache_read_mult is not None and p is None:
                    _note(notes, f"claude_code: unknown task profile {profile!r} in "
                                 "pricing.json — no estimate")
                continue
            spec = models[model_id]
            rate_in = spec["input_per_mtok"]
            rate_out = spec["output_per_mtok"]
            usd = (
                p["input_tokens"]
                * ((1 - cache_hit) * rate_in + cache_hit * rate_in * cache_read_mult)
                / 1e6
                + p["output_tokens"] / 1e6 * rate_out
            )
            slots[slot_name] = {"model": model_id, "usd_est": usd}
        est[profile] = slots
    return est


def _copilot_est(pricing, profiles, cache_hit, notes):
    """Copilot-side estimates via ``copilot_pricing.est_cost`` (USD + AIC)."""
    if pricing is None:
        _note(notes, "copilot_cli: pricing unavailable — no estimates")
        return None
    models = pricing.get("models", {})

    slot_models = {}
    for slot_name, tier_word in COPILOT_TIER_SLOTS:
        model_id = _first_model_of_tier(models, tier_word)
        slot_models[slot_name] = model_id
        if model_id is None:
            _note(notes, f"copilot_cli: no {tier_word}-tier model in "
                         f"pricing.copilot.json — {slot_name} slot has no estimate")

    est = {}
    for profile in profiles:
        slots = {}
        for slot_name, _tier_word in COPILOT_TIER_SLOTS:
            model_id = slot_models[slot_name]
            if model_id is None:
                slots[slot_name] = None
                continue
            try:
                r = cp.est_cost(pricing, profile, model_id, cache_hit=cache_hit)
            except KeyError:
                slots[slot_name] = None
                _note(notes, f"copilot_cli: no estimate for profile {profile!r} on "
                             f"{model_id} — unknown profile in pricing.copilot.json")
                continue
            slots[slot_name] = {
                "model": model_id,
                "usd_est": r["usd"],
                "aic_est": r["aic"],
            }
        est[profile] = slots
    return est


def _codex_est(pricing, profiles, cache_hit, notes):
    """Codex-side estimates via ``codex_pricing.resolve_tier`` + ``codex_pricing.est_cost``.
    Dollars are API-equivalent relative-burn proxies, never bills — every slot carries
    ``billed_usd: None``. Codex model ids are resolved from the dict at run time."""
    if pricing is None:
        _note(notes, "codex_cli: pricing unavailable — no estimates")
        return None

    slot_models = {}
    for slot_name, tier_word in CODEX_TIER_SLOTS:
        try:
            model_id = cxp.resolve_tier(pricing, tier_word)
        except KeyError:
            model_id = None
            _note(notes, f"codex_cli: no model at or above tier {tier_word!r} in "
                         f"pricing.codex.json — {slot_name} slot has no estimate")
        slot_models[slot_name] = model_id

    est = {}
    for profile in profiles:
        slots = {}
        for slot_name, _tier_word in CODEX_TIER_SLOTS:
            model_id = slot_models[slot_name]
            if model_id is None:
                slots[slot_name] = None
                continue
            try:
                r = cxp.est_cost(pricing, profile, model_id, cache_hit=cache_hit)
            except KeyError:
                slots[slot_name] = None
                _note(notes, f"codex_cli: no estimate for profile {profile!r} on "
                             f"{model_id} — unknown profile in pricing.codex.json")
                continue
            slots[slot_name] = {
                "model": model_id,
                "usd_api_equivalent": r["usd_api"],
                "billed_usd": None,
            }
        est[profile] = slots
    return est


# ---- public API ------------------------------------------------------------------------------

def build_harness_signal(reports, pricing_claude, pricing_copilot, pricing_codex,
                         profiles=ADVISOR_PROFILES, cache_hit=ADVISOR_CACHE_HIT):
    """Build the advisory ``signals.harness`` block (PLAN.md D5).

    ``reports`` is the digest's ``sources`` mapping (adapter reports; keys may be missing —
    tolerated via ``.get``). ``pricing_*`` are dicts or None. The three pricing files never
    merge; each harness's estimate uses ONLY its own file's rates.

    Returns exactly ``{"advisory": True, "note": ADVISORY_NOTE, "profiles": list(profiles),
    "cache_hit": cache_hit, "harnesses": {...}, "notes": [...]}`` with ``harnesses`` keyed
    ``claude_code``, ``copilot_cli``, ``codex_cli``. Purely advisory — nothing is executed
    or auto-pinned.
    """
    reports = reports or {}
    profiles = list(profiles)
    notes = []

    claude_est = _claude_est(pricing_claude, profiles, cache_hit, notes)
    copilot_est = _copilot_est(pricing_copilot, profiles, cache_hit, notes)
    codex_est = _codex_est(pricing_codex, profiles, cache_hit, notes)

    claude_r = reports.get("claude_code") or {}
    copilot_r = reports.get("copilot_cli") or {}
    codex_r = reports.get("codex_cli") or {}

    copilot_extra = copilot_r.get("extra") or {}
    codex_extra = codex_r.get("extra") or {}
    codex_proxy = codex_extra.get("codex_proxy") or {}

    harnesses = {
        "claude_code": {
            "available_today": bool(claude_r.get("available")),
            "sessions_today": claude_r.get("sessions", 0),
            "usd_today": claude_r.get("usd"),
            "billing": BILLING["claude_code"],
            "command_argv": list(COMMAND_ARGV["claude_code"]),
            "est": claude_est,
        },
        "copilot_cli": {
            "available_today": bool(copilot_r.get("available")),
            "sessions_today": copilot_r.get("sessions", 0),
            "usd_today": copilot_r.get("usd"),
            "aic_today": copilot_extra.get("aic"),
            "billing": BILLING["copilot_cli"],
            "command_argv": list(COMMAND_ARGV["copilot_cli"]),
            "est": copilot_est,
        },
        "codex_cli": {
            "available_today": bool(codex_r.get("available")),
            "sessions_today": codex_r.get("sessions", 0),
            # Codex is subscription usage-limited, not token-billed: usd_today is ALWAYS None.
            "usd_today": codex_r.get("usd"),
            "proxy_today": codex_proxy.get("api_equivalent_usd_total"),
            "billing": BILLING["codex_cli"],
            "command_argv": list(COMMAND_ARGV["codex_cli"]),
            "est": codex_est,
        },
    }

    return {
        "advisory": True,
        "note": ADVISORY_NOTE,
        "profiles": profiles,
        "cache_hit": cache_hit,
        "harnesses": harnesses,
        "notes": notes,
    }
