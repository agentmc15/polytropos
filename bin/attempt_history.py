#!/usr/bin/env python3
"""The attempt history: every dispatch every driver made, in one record shape, with what was
not observed left unknown.

WHAT WAS WRONG. Three records of the same work lived in three shapes that never met. The
attempt ledger (step 16) knows each dispatch. `NOTES.md` carries one `outcome:` line per
finished task, and the scorecard's reader keeps only the LAST line per task id, so a failed
run followed by a passing rerun read as if the failure had never happened. Codex writes typed
`role-use.jsonl` records for reviews that no reader parsed into role events at all, and Claude
and Copilot reviews left nothing but stdout. A consult that failed lost its parent at the
writer, because the `NOTES.md` grammar only carries `parent=` on a success. And a concrete
model id fell off a Claude-only alias ladder, so a valid Astra pass counted for nothing.

WHAT THIS IS. A read-only JOIN over those sources into one record per attempt (`RECORD_FIELDS`),
with two rules that do the work: every field is either observed or `None`, and `observed`
lists which -- so a missing observation stays missing rather than defaulting; and history is
never collapsed. `latest_state` is a PROJECTION computed from the history, kept beside it, so
a rerun's pass and the failure before it are both there to read. The same two rules govern the
provenance references an attempt may carry (`PROVENANCE_FIELDS`): a reference nobody recorded
is `None` and is COUNTED as unknown by `summarize`, because a reference that is merely missing
from a card is indistinguishable from one that was never asked for.

WHAT IT REFUSES. It does not price anything: cost rides in from the records that carried one,
under its own basis (`COST_BASES`), and bases are never summed together -- an estimated dollar
and a billed dollar are different facts. A cost a model wrote into its own output is
`model-reported`, kept apart from everything the driver measured. It reads no transcript, no
home directory, and no report text; the only free text it carries is what the ledger already
bounded and redacted.
"""

import importlib.util
import json
import re
import sys
from pathlib import Path

HISTORY_VERSION = "polytropos.attempt-history/1"

#: Where a record came from. `ledger+role-use` is one dispatch seen by both.
SOURCES = ("ledger", "notes", "role-use", "ledger+role-use")

#: Cost bases. Never summed across each other.
COST_BASES = ("billed", "credits", "estimated", "proxy", "model-reported")

#: One record per attempt. Every field is observed or None; `observed` names the former.
#:
#: The four `*_ref` fields are the attempt's PROVENANCE and must stay exactly
#: `attempt_ledger.PROVENANCE_REFS` -- the ledger owns which references an event may carry, this
#: tuple owns which the record projects, and `tests/test_decision_provenance.py` fails if the two
#: ever drift. They are listed literally here for the same reason every other field is: `observe`
#: raises `KeyError` for a key absent from this tuple, so a reference written to the ledger and
#: missing from here could not be projected at all.
RECORD_FIELDS = (
    "kit", "run", "task", "attempt", "source", "harness", "op", "role", "phase",
    "requested_model", "dispatched_model", "observed_model", "effort",
    "tier", "tier_harness", "registry_version", "ts", "result", "failure_class",
    "verify_rc", "verify_signature", "verify_failures", "artifact", "parent",
    "acceptance_ref", "policy_ref", "decision_ref", "admission_ref",
    "attempts_recorded", "ledger_attempts", "cost", "observed",
)

#: The subset of `RECORD_FIELDS` whose absence `summarize` counts as unknown provenance. A
#: reference nothing recorded has to be DISCLOSED, not silently missing: a record that simply
#: lacks the field looks identical to one that carries nothing, and only the count tells the
#: reader which question was never answered.
PROVENANCE_FIELDS = ("acceptance_ref", "policy_ref", "decision_ref", "admission_ref")

#: What each driver calls itself in `run.started` -> the harness whose pricing file it reads.
ACTOR_HARNESS = {"claude-code": "claude", "codex": "codex", "copilot": "copilot",
                 "ralph": "copilot"}

OUTCOME_RE = re.compile(r"^\s*(?:[-*]\s+)?outcome:\s+(\S+)\s+(.+)$")
BUDGET_RE = re.compile(r"^\s*(?:[-*]\s+)?budget:\s+(.+)$")
PAIR_RE = re.compile(r"(\w+)=(\S+)")
RESULTS = ("pass", "retry-pass", "escalated-pass", "blocked", "budget-stop")


# ---- sibling loaders (bin/ is not a package) -------------------------------------------------

_MODS = {}


def _mod(name):
    if name not in _MODS:
        path = Path(__file__).resolve().parent / f"{name}.py"
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _MODS[name] = mod
    return _MODS[name]


# ---- records ------------------------------------------------------------------------------------

def blank():
    rec = {field: None for field in RECORD_FIELDS}
    rec["observed"] = []
    return rec


def observe(rec, **fields):
    """Set fields on `rec` and note them as observed; a None value is not an observation."""
    for key, value in fields.items():
        if key not in RECORD_FIELDS:
            raise KeyError(f"attempt history: {key!r} is not a record field")
        if value is None:
            continue
        rec[key] = value
        if key not in rec["observed"]:
            rec["observed"].append(key)
    return rec


def _tier(rec, registry):
    """Resolve the record's dispatched model through the registry, harness-hinted."""
    model = rec.get("dispatched_model") or rec.get("requested_model")
    if not model:
        return
    hit = registry.resolve(model, harness=rec.get("harness")) or registry.resolve(model)
    if not hit:
        return
    observe(rec, tier=hit.get("tier"),
            tier_harness=hit.get("harness"),
            registry_version=hit.get("registry"))
    if rec.get("harness") is None and hit.get("harness"):
        # The model is known to exactly one harness; that is an observation about the
        # record, and it is labelled as inferred from the registry rather than recorded.
        observe(rec, harness=hit["harness"])
        rec["observed"].append("harness:inferred-from-model")


# ---- sources ------------------------------------------------------------------------------------

def _cost(basis, usd=None, credits=None, source=""):
    return {"basis": basis, "usd": usd, "credits": credits, "source": source}


def ledger_records(kit, ledger, registry):
    """One record per attempt in a kit's ledger, plus actor identity from `run.started`."""
    events = ledger.events()
    actor_by_run = {}
    for ev in events:
        if ev.get("kind") == "run.started" and ev.get("run"):
            actor_by_run[ev["run"]] = ev.get("actor")
    tasks = []
    for ev in events:
        if ev.get("kind") == "attempt.started" and ev.get("task") not in tasks:
            tasks.append(ev.get("task"))
    records = []
    for task in tasks:
        for h in ledger.task_history(task):
            started = h.get("started") or {}
            finished = h.get("finished") or {}
            verify = h.get("verify") or {}
            rec = blank()
            actor = started.get("actor") or actor_by_run.get(started.get("run"))
            observe(rec, kit=kit, run=started.get("run"), task=task, attempt=h["attempt"],
                    source="ledger", harness=ACTOR_HARNESS.get(actor, actor),
                    op=started.get("op"), role=started.get("role"),
                    phase=started.get("phase"), requested_model=started.get("requested_model"),
                    dispatched_model=started.get("model"), effort=started.get("effort"),
                    ts=started.get("ts"), artifact=started.get("artifact"),
                    parent=started.get("parent"))
            # Provenance rides the `attempt.started` line, read through its one owner so this
            # module never re-derives the reference shape. Absent stays absent: `observe`
            # declines a None, so an attempt recorded before these existed is counted as
            # unknown by `summarize` rather than filled in here.
            observe(rec, **_mod("attempt_ledger").provenance(started))
            if finished:
                observe(rec, observed_model=finished.get("observed_model"),
                        failure_class=finished.get("class"))
                if finished.get("cost_usd") is not None:
                    basis = ("model-reported" if finished.get("cost_source") == "parsed"
                             else "estimated")
                    observe(rec, cost=_cost(basis, usd=float(finished["cost_usd"]),
                                            source="ledger"))
            if verify:
                observe(rec, verify_rc=verify.get("rc"), verify_signature=verify.get("signature"),
                        verify_failures=verify.get("failures"))
            if not finished:
                result = "open"
            elif finished.get("outcome") == "unknown":
                result = "unknown"
            elif finished.get("class"):
                result = "dispatch-failed"
            elif verify:
                result = "pass" if verify.get("rc") == 0 else "verify-failed"
            elif finished.get("result"):
                result = finished["result"]
            else:
                result = "dispatched"
            observe(rec, result=result)
            _tier(rec, registry)
            records.append(rec)
    return records


def _notes_blocks(text):
    """NOTES.md split into `## ` blocks -> `[(head_line, block_lines)]`."""
    blocks = []
    head, lines = None, []
    for line in (text or "").splitlines():
        if line.startswith("## "):
            if head is not None or lines:
                blocks.append((head, lines))
            head, lines = line, []
        else:
            lines.append(line)
    if head is not None or lines:
        blocks.append((head, lines))
    return blocks


def _harness_hint(lines):
    """Which driver wrote a NOTES.md block, from the fields only that driver writes."""
    has_role = any(ln.strip().startswith("- role:") for ln in lines)
    has_agent = any(ln.strip().startswith("- agent:") for ln in lines)
    has_planned = any(ln.strip().startswith("- planned model:") for ln in lines)
    if has_planned:
        return "codex"
    if has_agent and not has_role:
        return "copilot"
    if has_role:
        return None  # Claude or Codex both write `- role:`; the model id may tell them apart
    return None


def notes_records(kit, text, registry):
    """One record per `outcome:` line in NOTES.md -- EVERY line, never last-wins."""
    records = []
    index = 0
    for head, lines in _notes_blocks(text):
        hint = _harness_hint(lines)
        cost = None
        failure_class = None
        for ln in lines:
            s = ln.strip()
            if s.startswith("- failure-class:"):
                failure_class = s[len("- failure-class:"):].strip() or None
            bm = BUDGET_RE.match(ln)
            if bm:
                pairs = dict(PAIR_RE.findall(bm.group(1)))
                raw = pairs.get("est_actual_usd")
                try:
                    usd = float(raw) if raw not in (None, "unpriced", "not-counted") else None
                except ValueError:
                    usd = None
                if usd is not None:
                    cost = _cost("estimated", usd=usd, source="notes:budget")
        for ln in lines:
            m = OUTCOME_RE.match(ln)
            if not m:
                continue
            index += 1
            pairs = dict(PAIR_RE.findall(m.group(2)))
            result = pairs.get("result")
            if not pairs.get("model") or result not in RESULTS:
                continue
            rec = blank()
            try:
                attempts = int(pairs.get("attempts", "1"))
            except ValueError:
                attempts = None
            ts = head.split(" — ", 1)[0][3:].strip() if head and " — " in head else None
            observe(rec, kit=kit, run=pairs.get("run"), task=m.group(1),
                    attempt=f"notes:{index}", source="notes", harness=hint,
                    op="task", dispatched_model=pairs.get("model"), ts=ts, result=result,
                    parent=pairs.get("parent"), attempts_recorded=attempts,
                    failure_class=failure_class or pairs.get("failure"), cost=cost)
            _tier(rec, registry)
            records.append(rec)
    return records


def role_use_records(kit, raw_records, registry):
    """Codex's typed review/acceptance records as attempt records."""
    records = []
    for r in raw_records:
        if not isinstance(r, dict) or r.get("schema") != "polytropos.role-use/1":
            continue
        rec = blank()
        role = r.get("role")
        observe(rec, kit=kit, run=r.get("run_id"), task=f"phase-{r.get('phase')}",
                attempt=f"role-use:{r.get('phase')}:{role}:{r.get('attempt')}",
                source="role-use", harness="codex",
                op="acceptance" if role == "orchestrator" else "review", role=role,
                phase=str(r.get("phase")) if r.get("phase") is not None else None,
                requested_model=r.get("planned_model"), dispatched_model=r.get("dispatched_model"),
                observed_model=r.get("actual_model"), ts=r.get("recorded_at"),
                artifact=r.get("evidence_fingerprint"))
        rc = r.get("dispatch_rc")
        if r.get("result"):
            observe(rec, result=r["result"])
        elif isinstance(rc, int) and not isinstance(rc, bool):
            observe(rec, result="ok" if rc == 0 else "failed")
        _tier(rec, registry)
        records.append(rec)
    return records


# ---- the join -------------------------------------------------------------------------------------

def read_kit(kit_dir, store=None):
    """One kit's raw sources, read-only -> dict. Missing pieces are absent, not invented."""
    kit_dir = Path(kit_dir)
    out = {"kit": kit_dir.name, "dir": kit_dir, "notes_text": "", "role_use": [],
           "ledger": None, "notes": []}
    notes_path = kit_dir / "NOTES.md"
    if notes_path.is_file():
        out["notes_text"] = notes_path.read_text(errors="replace")
    role_use = kit_dir / "role-use.jsonl"
    if role_use.is_file():
        for line in role_use.read_text(errors="replace").splitlines():
            try:
                obj = json.loads(line)
            except ValueError:
                out["notes"].append(f"{kit_dir.name}: unparseable role-use line skipped")
                continue
            if isinstance(obj, dict):
                out["role_use"].append(obj)
    kc = _mod("kit_contract")
    try:
        ledger = kc.open_ledger(kit_dir, store=store)
    except Exception as exc:  # noqa: BLE001 -- an unopenable ledger is a coverage fact
        out["notes"].append(f"{kit_dir.name}: attempt ledger unavailable ({exc})")
        ledger = None
    if ledger is not None and ledger.events_path.exists():
        out["ledger"] = ledger
    return out


def join_kit(kit_dir, store=None, registry=None):
    """Every attempt record for one kit, joined and deduplicated -> `(records, notes)`."""
    registry = registry or _mod("model_registry").registry()
    raw = read_kit(kit_dir, store=store)
    kit = raw["kit"]
    notes = list(raw["notes"])
    ledger_recs = ledger_records(kit, raw["ledger"], registry) if raw["ledger"] else []
    notes_recs = notes_records(kit, raw["notes_text"], registry)
    role_recs = role_use_records(kit, raw["role_use"], registry)
    if raw["ledger"] and raw["ledger"].corrupt:
        notes.append(f"{kit}: {raw['ledger'].corrupt} unparseable ledger line(s) skipped")

    # Reviews seen by both the ledger and Codex's typed record are ONE dispatch: keep the
    # ledger record and fill what only the typed record observed.
    by_key = {}
    for rec in ledger_recs:
        if rec["op"] in ("review", "acceptance") and rec["run"]:
            by_key[(rec["run"], rec["phase"], rec["role"])] = rec
    merged_role = []
    for rec in role_recs:
        key = (rec["run"], rec["phase"], rec["role"])
        target = by_key.get(key) if rec["run"] else None
        if target is None:
            merged_role.append(rec)
            continue
        for field in ("observed_model", "requested_model", "artifact", "result"):
            if target.get(field) is None and rec.get(field) is not None:
                observe(target, **{field: rec[field]})
        target["source"] = "ledger+role-use"

    # A NOTES.md outcome line is the projection of the ledger's attempts for that run and
    # task. Link them, and say when the line's own count disagrees with what was recorded.
    ledger_by_run_task = {}
    harness_by_run = {}
    for rec in ledger_recs:
        if rec.get("harness") and rec["run"]:
            harness_by_run.setdefault(rec["run"], rec["harness"])
        if rec["op"] not in ("review", "acceptance"):
            ledger_by_run_task.setdefault((rec["run"], rec["task"]), []).append(rec["attempt"])
    for rec in notes_recs:
        ids = ledger_by_run_task.get((rec["run"], rec["task"])) if rec["run"] else None
        if ids:
            observe(rec, ledger_attempts=list(ids))
            if rec.get("attempts_recorded") not in (None, len(ids)):
                notes.append(
                    f"{kit}: outcome {rec['task']} run {rec['run']} says attempts="
                    f"{rec['attempts_recorded']} but the ledger holds {len(ids)}; both kept"
                )
        # The line is that run's projection, so the run's recorded actor is its harness --
        # a join, not a guess -- and it outranks a harness inferred from the model id alone.
        # The tier is then resolved again, hinted by the harness that actually ran it.
        from_run = harness_by_run.get(rec["run"]) if rec["run"] else None
        inferred = "harness:inferred-from-model" in rec["observed"]
        if from_run and (rec.get("harness") is None or inferred):
            if inferred:
                rec["observed"].remove("harness:inferred-from-model")
            rec["harness"] = from_run
            if "harness" not in rec["observed"]:
                rec["observed"].append("harness")
            rec["observed"].append("harness:from-ledger-run")
            for field in ("tier", "tier_harness", "registry_version"):
                rec[field] = None
                if field in rec["observed"]:
                    rec["observed"].remove(field)
            _tier(rec, registry)

    records = ledger_recs + merged_role + notes_recs
    seen = set()
    unique = []
    for rec in records:
        key = (rec["kit"], rec["source"], rec["attempt"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(rec)
    return unique, notes


def join_kits(kits_dir, store=None, registry=None):
    """Every kit under `kits_dir`, sorted by name -> `(records, notes, coverage)`."""
    registry = registry or _mod("model_registry").registry()
    kits_dir = Path(kits_dir)
    if not kits_dir.is_dir():
        raise ValueError(f"no kits dir at {kits_dir}")
    records, notes = [], []
    coverage = {"kits": 0, "kits_with_ledger": 0, "kits_with_notes": 0,
                "kits_with_role_use": 0}
    for sub in sorted((p for p in kits_dir.iterdir() if p.is_dir()), key=lambda p: p.name):
        if not (sub / "TASKS.md").is_file():
            continue
        coverage["kits"] += 1
        raw = read_kit(sub, store=store)
        coverage["kits_with_ledger"] += 1 if raw["ledger"] else 0
        coverage["kits_with_notes"] += 1 if raw["notes_text"].strip() else 0
        coverage["kits_with_role_use"] += 1 if raw["role_use"] else 0
        recs, kit_notes = join_kit(sub, store=store, registry=registry)
        records.extend(recs)
        notes.extend(kit_notes)
    return records, notes, coverage


# ---- projections ------------------------------------------------------------------------------

def latest_state(records):
    """Per (kit, task): the latest verdict from NOTES.md lines -> dict. A projection.

    Last line wins, except that a `budget-stop` never supersedes a recorded verdict -- the
    same rule the scorecard's reader applies. History is untouched by this.
    """
    latest = {}
    for rec in records:
        if rec["source"] != "notes":
            continue
        key = f"{rec['kit']}/{rec['task']}"
        prior = latest.get(key)
        if (rec["result"] == "budget-stop" and prior is not None
                and prior["result"] != "budget-stop"):
            continue
        latest[key] = {"result": rec["result"], "model": rec["dispatched_model"],
                       "run": rec["run"], "attempt": rec["attempt"]}
    return latest


def lineage(records):
    """Consults grouped under the task they were spawned to rescue -> list of chains.

    Ledger records keep `parent` on EVERY result, so a failed consult stays in its chain;
    NOTES.md lines carry it only on `escalated-pass`, by that grammar's rule. A chain is
    `rescued` when any child passed and `unrescued` otherwise, and its `attempts` is the
    whole chain's -- the original pin's failure is part of the cost of the rescue, never a
    free pass for the cheap choice.
    """
    chains = {}
    for rec in records:
        parent = rec.get("parent")
        if not parent:
            continue
        key = (rec["kit"], parent)
        chain = chains.setdefault(key, {"kit": rec["kit"], "parent": parent, "children": [],
                                        "verdict": "unrescued", "attempts": 0})
        chain["children"].append({"task": rec["task"], "source": rec["source"],
                                  "model": rec["dispatched_model"], "tier": rec["tier"],
                                  "result": rec["result"], "run": rec["run"]})
        if rec["result"] in ("pass", "retry-pass", "escalated-pass"):
            chain["verdict"] = "rescued"
    for chain in chains.values():
        kit, parent = chain["kit"], chain["parent"]
        for rec in records:
            if rec["kit"] != kit:
                continue
            if rec["task"] == parent or rec.get("parent") == parent:
                if rec["source"] == "ledger":
                    chain["attempts"] += 1
                elif rec["source"] == "notes" and not rec.get("ledger_attempts"):
                    chain["attempts"] += rec.get("attempts_recorded") or 1
    return list(chains.values())


def cost_totals(records):
    """Per-basis totals and coverage. Bases are never added to each other."""
    totals = {basis: {"n": 0, "usd": None, "credits": None} for basis in COST_BASES}
    with_cost = 0
    for rec in records:
        cost = rec.get("cost")
        if not cost:
            continue
        basis = cost.get("basis")
        if basis not in totals:
            continue
        with_cost += 1
        totals[basis]["n"] += 1
        for field in ("usd", "credits"):
            value = cost.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                current = totals[basis][field]
                totals[basis][field] = round((current or 0.0) + float(value), 6)
    return {"by_basis": totals, "records_with_cost": with_cost, "records": len(records),
            "note": "bases are separate facts and are never summed together"}


def summarize(records, notes=(), coverage=None, registry=None):
    """The card: what the joined history shows, with unknowns counted, never filled."""
    registry = registry or _mod("model_registry").registry()
    by_harness = {}
    unknown = {"harness": 0, "tier": 0, "observed_model": 0, "cost": 0}
    unknown.update({field: 0 for field in PROVENANCE_FIELDS})
    classes = {}
    by_source = {}
    for rec in records:
        by_source[rec["source"]] = by_source.get(rec["source"], 0) + 1
        harness = rec.get("harness") or "unknown"
        tier = rec.get("tier") or "unknown"
        if rec.get("harness") is None:
            unknown["harness"] += 1
        if rec.get("tier") is None:
            unknown["tier"] += 1
        if rec.get("observed_model") is None and rec["source"] != "notes":
            unknown["observed_model"] += 1
        if rec.get("cost") is None:
            unknown["cost"] += 1
        for field in PROVENANCE_FIELDS:
            if rec.get(field) is None:
                unknown[field] += 1
        if rec.get("failure_class"):
            classes[rec["failure_class"]] = classes.get(rec["failure_class"], 0) + 1
        h = by_harness.setdefault(harness, {"records": 0, "tiers": {}})
        h["records"] += 1
        t = h["tiers"].setdefault(tier, {"records": 0, "results": {}})
        t["records"] += 1
        result = rec.get("result") or "unknown"
        t["results"][result] = t["results"].get(result, 0) + 1
    return {
        "schema": HISTORY_VERSION,
        "records": len(records),
        "by_source": by_source,
        "by_harness": by_harness,
        "unknown": unknown,
        "failure_classes": classes,
        "lineage": lineage(records),
        "latest": latest_state(records),
        "cost": cost_totals(records),
        "coverage": coverage or {},
        "registry": registry.versions(),
        "notes": list(notes),
    }


def render_markdown(card):
    lines = [f"# Attempt history ({card['schema']})", ""]
    lines.append(f"records: {card['records']}  sources: "
                 + ", ".join(f"{k}={v}" for k, v in sorted(card["by_source"].items())))
    cov = card.get("coverage") or {}
    if cov:
        lines.append(f"kits: {cov.get('kits', 0)} (ledger {cov.get('kits_with_ledger', 0)}, "
                     f"notes {cov.get('kits_with_notes', 0)}, role-use "
                     f"{cov.get('kits_with_role_use', 0)})")
    lines.append(f"registry: " + ", ".join(f"{h}@{v}" for h, v in sorted(card["registry"].items())))
    lines.append("")
    lines.append("## By harness and tier")
    for harness, h in sorted(card["by_harness"].items()):
        lines.append(f"- {harness}: {h['records']} record(s)")
        for tier, t in sorted(h["tiers"].items()):
            results = ", ".join(f"{k}={v}" for k, v in sorted(t["results"].items()))
            lines.append(f"    - {tier}: {t['records']} ({results})")
    u = card["unknown"]
    lines.append("")
    lines.append(f"unknown: harness={u['harness']} tier={u['tier']} "
                 f"observed_model={u['observed_model']} cost={u['cost']}  "
                 f"(counted, never filled)")
    lines.append("unknown provenance: " + " ".join(
        f"{field.removesuffix('_ref')}={u.get(field, 0)}" for field in PROVENANCE_FIELDS)
        + "  (no reference recorded; unknown, never inferred)")
    if card["failure_classes"]:
        lines.append("failure classes: " + ", ".join(
            f"{k}={v}" for k, v in sorted(card["failure_classes"].items())))
    if card["lineage"]:
        lines.append("")
        lines.append("## Lineage")
        for chain in card["lineage"]:
            kids = "; ".join(f"{c['task']}@{c['model'] or '?'}:{c['result']}"
                             for c in chain["children"])
            lines.append(f"- {chain['kit']}/{chain['parent']}: {chain['verdict']} after "
                         f"{chain['attempts']} attempt(s) in the chain ({kids})")
    c = card["cost"]
    lines.append("")
    lines.append(f"## Cost ({c['records_with_cost']} of {c['records']} records carry one)")
    for basis, t in c["by_basis"].items():
        if t["n"]:
            usd = "n/a" if t["usd"] is None else f"${t['usd']:.4f}"
            lines.append(f"- {basis}: n={t['n']} usd={usd}")
    lines.append(f"  {c['note']}")
    if card["notes"]:
        lines.append("")
        lines.append("## Notes")
        lines.extend(f"- {n}" for n in card["notes"])
    return "\n".join(lines)


# ---- CLI ----------------------------------------------------------------------------------------------

DEMO_TASKS_MD = """# TASKS — {kit} (synthetic)

## Phase 1 — demo

### T1 — First
- status: done
- model: {model}

**Brief.** Synthetic.

**Verify.**
```bash
true
```

### T2 — Second
- status: blocked
- model: {model}

**Brief.** Synthetic.

**Verify.**
```bash
true
```
"""


def _demo(as_json):
    """Three synthetic kits in a temp dir: a Claude kit with ledger and notes on concrete
    ids, a legacy Copilot kit with notes only, and a Codex kit with a typed review record.
    Spends nothing, reads no real store."""
    import tempfile
    mr = _mod("model_registry")
    al = _mod("attempt_ledger")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        kits = root / "kits"
        store = root / "store"
        # Kit A: Claude, concrete ids, a failed run then a passing rerun, and a failed consult.
        a = kits / "alpha"
        a.mkdir(parents=True)
        (a / "TASKS.md").write_text(DEMO_TASKS_MD.format(kit="alpha", model="claude-opus-5"))
        ledger = al.AttemptLedger(store, "alpha")
        ledger.append("run.started", run="r1", task="T1", actor="claude-code", pid=1)
        x = ledger.record_started("r1", "T1", "initial", "claude-opus-5", role="implementer",
                                  requested_model="claude-opus-5", actor="claude-code")
        ledger.record_finished("r1", "T1", x, "ok", 0, "tried")
        ledger.record_verify("r1", "T1", x, 1, "FAILED (failures=2)")
        ledger.record_projected("r1", "T1", "blocked", "blocked", outcome_line=True)
        ledger.append("run.started", run="r2", task="T1", actor="claude-code", pid=1)
        y = ledger.record_started("r2", "T1", "retry", "claude-opus-5", role="implementer",
                                  requested_model="claude-opus-5", actor="claude-code")
        ledger.record_finished("r2", "T1", y, "ok", 0, "fixed")
        ledger.record_verify("r2", "T1", y, 0, "OK")
        ledger.record_projected("r2", "T1", "done", "pass", outcome_line=True)
        ledger.append("run.started", run="r3", task="T2", actor="claude-code", pid=1)
        z = ledger.record_started("r3", "T2", "consult", "claude-fable-5", role="implementer",
                                  parent="T1", requested_model="claude-fable-5",
                                  actor="claude-code")
        ledger.record_finished("r3", "T2", z, "failed", 1, "Error: Not logged in", cls="auth")
        (a / "NOTES.md").write_text(
            "## 2026-01-01T00:00:00Z — T1\n- role: implementer\n- verify: exit 1\n"
            "- outcome: T1 model=claude-opus-5 attempts=1 result=blocked review=none run=r1\n\n"
            "## 2026-01-02T00:00:00Z — T1\n- role: implementer\n- verify: exit 0\n"
            "- outcome: T1 model=claude-opus-5 attempts=1 result=pass review=none run=r2\n\n"
            "## 2026-01-03T00:00:00Z — T2\n- role: implementer\n- failure-class: auth\n"
            "- outcome: T2 model=claude-fable-5 attempts=1 result=blocked review=none run=r3\n"
        )
        # Kit B: legacy Copilot, notes only, with an estimated budget line.
        b = kits / "beta"
        b.mkdir()
        (b / "TASKS.md").write_text(DEMO_TASKS_MD.format(kit="beta", model="gpt-5.6-terra"))
        (b / "NOTES.md").write_text(
            "## 2026-01-04T00:00:00Z — T1\n- agent: implementer\n- verify: exit 0\n"
            "- budget: standard=gpt-5.6-sol actual=gpt-5.6-terra profile=S "
            "est_standard_usd=0.0400 est_actual_usd=0.0100 delta_usd=-0.0300 status=done\n"
            "- outcome: T1 model=gpt-5.6-terra attempts=1 result=pass review=none run=c1\n"
        )
        # Kit C: Codex, a typed review record joined with its ledger twin.
        c = kits / "gamma"
        c.mkdir()
        (c / "TASKS.md").write_text(DEMO_TASKS_MD.format(kit="gamma", model="gpt-6-astra"))
        (c / "role-use.jsonl").write_text(json.dumps({
            "schema": "polytropos.role-use/1", "recorded_at": "2026-01-05T00:00:00Z",
            "phase": "1", "role": "verifier", "run_id": "g1", "attempt": 1, "dispatch_rc": 0,
            "planned_model": None, "dispatched_model": "gpt-5.6-sol",
            "actual_model": "gpt-5.6-sol", "actual_role": "verifier", "result": None,
            "evidence_fingerprint": "abc", "report_sha256": "def"}) + "\n")
        kc = _mod("kit_contract")
        kc.record_role_dispatch(c, "g1", "verifier", "1", "gpt-5.6-sol", 0, "looks fine",
                                actor="codex", store=store)
        records, notes, coverage = join_kits(kits, store=store, registry=mr.registry())
        card = summarize(records, notes, coverage, registry=mr.registry())
        print(json.dumps(card, indent=2, sort_keys=True) if as_json else render_markdown(card))
    return 0


def _cli(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        prog="attempt_history.py",
        description="Every dispatch every driver made, joined across the attempt ledger, "
                    "NOTES.md outcome lines and Codex role-use records, with unknowns kept. "
                    "`demo` is synthetic and touches no real store.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="synthetic walkthrough in a temp dir")
    d.add_argument("--json", action="store_true")
    s = sub.add_parser("show", help="join every kit under a kits dir")
    s.add_argument("--kits-dir", required=True)
    s.add_argument("--attempt-store", default=None,
                   help="ledger root (default: the per-user data root for each kit's checkout)")
    s.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "demo":
        return _demo(args.json)
    records, notes, coverage = join_kits(args.kits_dir, store=args.attempt_store)
    card = summarize(records, notes, coverage)
    print(json.dumps(card, indent=2, sort_keys=True) if args.json else render_markdown(card))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
