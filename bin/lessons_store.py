#!/usr/bin/env python3
"""Scoped lessons: observations with provenance and expiry, rules only by evidence or by ask.

WHAT WAS THE MATTER, MEASURED. `copilot/.github/skills/lessons-loop/SKILL.md` said: on a
correction or an escalation, append a lesson to `tasks/lessons.md`; at session start, read
the file and apply it. The `route` skill and the `route` agent then said: a lesson that
names this task's shape OVERRIDES the default tier. So one escalation -- a cheap model that
failed once on one refactor in one repository -- became, the same day, a startup rule that
moved every later refactor up a tier, with no record of where it came from, no scope, no
expiry, and no way to say it had stopped being true. That is the roadmap's "a single
escalation must not become a universal model-tier rule", and it was the default path.

WHAT THIS MODULE DOES. The file stays where it was and stays JSON lines, one object per line,
appended and never rewritten. Every entry now has a KIND:

  observation  what happened, once, with provenance (source, kit, task, run), scope
               (project, providers, task shape), and an expiry. Retrieved as a candidate,
               labelled as one; never applied as a rule.
  rule         a lesson that may be applied. Made only by `promote`, which either records an
               explicit user requirement (`--by user`) or finds RECURRENCE: at least
               `RECURRENCE_GATE` observations of the same lesson from distinct kits or tasks,
               all cited as the rule's evidence.
  contest      evidence against a rule. A contested rule is withheld at recall until a human
               re-promotes it; the contest itself is kept, because a rule that was wrong once
               is worth remembering as such.
  legacy       an entry written before kinds existed. Retrieved as an observation, never as
               a rule, so a startup rule that never had evidence stops being one without
               anyone editing history.

`recall` returns only what is ELIGIBLE (the same project/provider rule as `bin/memory_recall.py`
uses for memory, reused rather than copied), not expired, not contested, matching the asked
`applies_to` and task shape, and within a budget of entries and characters -- rules first, then
candidates, each with its provenance in the header so a reader never mistakes a candidate for
an instruction. `review` reports what is expired, contested, promotable, and legacy.

WHAT IT NEVER DOES. It dispatches nothing, prices nothing, reads no home directory, and
promotes nothing on its own: `observe` records, `promote` needs evidence or an explicit ask,
and nothing in a session start turns an observation into a rule. `bin/lessons_promote.py`
stays the draft tool for defect-kind recurrence across kits; this module is the store the
Copilot lessons skill and the route agent read.
"""

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path

SCHEMA = "polytropos.lessons/2"
KINDS = ("observation", "rule", "contest", "legacy")
SOURCES = ("user-correction", "escalation", "reviewer", "verifier", "operator", "legacy")
DEFAULT_FILE = Path("tasks") / "lessons.md"

#: An observation is a candidate for this long; a rule never expires on its own. The number
#: is a policy default, overridable per entry, not a fact about anything.
DEFAULT_EXPIRY_DAYS = 90

#: The same gate `bin/lessons_promote.py` applies to defect kinds: two distinct sources are
#: the smallest recurrence there is. One observation is an anecdote.
RECURRENCE_GATE = 2

#: What a session start may receive. A budget that is never reached is not a budget.
BUDGET_ENTRIES = 8
BUDGET_CHARS = 2000


class LessonsError(ValueError):
    """A request the store cannot honour: a bad date, an unknown id, a promotion without
    evidence, a kind or source outside the vocabulary."""


def _memory_recall():
    path = Path(__file__).resolve().with_name("memory_recall.py")
    spec = importlib.util.spec_from_file_location("polytropos_memory_recall", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_date(text, what="date"):
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError) as exc:
        raise LessonsError(f"{what} must be YYYY-MM-DD, got {text!r}") from exc


def new_id(day, failure_pattern):
    """A content-derived id: date plus six hex of the pattern, so the same observation made
    twice on one day is the same id and a reader can tell one entry from another by eye."""
    digest = hashlib.sha256(f"{day}|{failure_pattern}".encode("utf-8")).hexdigest()[:6]
    return f"L-{day}-{digest}"


# ---- the file -------------------------------------------------------------------------------------

def load(path):
    """Every entry in `path` -> `(entries, notes)`. Legacy entries get `kind: legacy` and a
    line-derived id; a malformed line is a note, never a crash; a missing file is empty."""
    p = Path(path)
    entries, notes = [], []
    if not p.is_file():
        notes.append(f"lessons file not found: {p}")
        return entries, notes
    for i, raw in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            notes.append(f"line {i}: malformed JSON, skipped ({exc})")
            continue
        if not isinstance(obj, dict) or "lesson" not in obj:
            notes.append(f"line {i}: missing required field(s), skipped")
            continue
        entry = dict(obj)
        if entry.get("kind") not in KINDS:
            entry["kind"] = "legacy"
            entry.setdefault("id", f"legacy-{i}")
            entry.setdefault("provenance", {"source": "legacy"})
            entry.setdefault("scope", {})
            entry.setdefault("expires", "never")
        entry.setdefault("applies_to", [])
        entry.setdefault("evidence", [])
        entry["_line"] = i
        entries.append(entry)
    return entries, notes


def _append(path, entry):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return entry


def _by_id(entries):
    return {e["id"]: e for e in entries if e.get("id")}


# ---- writing ---------------------------------------------------------------------------------------

def observe(path, now, failure_pattern, lesson, applies_to=(), source="operator", kit=None,
            task=None, run=None, project=None, providers=(), task_shape=None, expires=None):
    """Record what happened, once, as a candidate -> the entry appended.

    Provenance says where it came from; scope says where it applies; the expiry (default
    `DEFAULT_EXPIRY_DAYS` from `now`) says how long a candidate stays interesting without
    recurring. Nothing here is a rule.
    """
    day = parse_date(now, "--now")
    if source not in SOURCES:
        raise LessonsError(f"source {source!r} is not one of {', '.join(SOURCES)}")
    if not failure_pattern or not lesson:
        raise LessonsError("an observation needs both a failure_pattern and a lesson")
    if expires is None:
        expires = (day + timedelta(days=DEFAULT_EXPIRY_DAYS)).isoformat()
    elif expires != "never":
        parse_date(expires, "--expires")
    entry = {
        "v": SCHEMA,
        "id": new_id(day.isoformat(), failure_pattern),
        "kind": "observation",
        "date": day.isoformat(),
        "failure_pattern": failure_pattern,
        "lesson": lesson,
        "applies_to": sorted(set(applies_to)),
        "scope": {"project": project or "", "providers": ",".join(providers) or "any",
                  "task_shape": task_shape or ""},
        "provenance": {"source": source, "kit": kit, "task": task, "run": run},
        "expires": expires,
        "evidence": [],
    }
    return _append(path, entry)


def _distinct_sources(observations):
    """How many independent places a lesson was observed: distinct (kit, task) pairs, or
    distinct sources when neither is recorded."""
    keys = set()
    for o in observations:
        prov = o.get("provenance") or {}
        keys.add((prov.get("kit"), prov.get("task"), prov.get("run") if not prov.get("kit")
                  else None))
    return len(keys)


def _same_lesson(a, b):
    return (a.get("lesson", "").strip().lower() == b.get("lesson", "").strip().lower()
            and sorted(a.get("applies_to", [])) == sorted(b.get("applies_to", [])))


def _live_observations(entries, now):
    day = parse_date(now, "--now")
    out = []
    for e in entries:
        if e["kind"] not in ("observation", "legacy"):
            continue
        if e.get("superseded_by"):
            continue
        if _expired(e, day):
            continue
        out.append(e)
    return out


def _expired(entry, day):
    expires = entry.get("expires") or "never"
    if expires == "never":
        return False
    try:
        return date.fromisoformat(expires) <= day
    except ValueError:
        return False


def promote(path, now, observation_id=None, by="recurrence", note=""):
    """Turn observations into a rule -> the rule appended.

    `by="user"` records an explicit requirement: the named observation becomes a rule with
    that one entry as evidence and `promoted_by: user`. `by="recurrence"` needs the named
    observation to recur: at least `RECURRENCE_GATE` live observations with the same lesson
    and `applies_to`, from distinct kits or tasks; the rule cites every one. Anything less is
    refused with the count, because one escalation is not a rule.
    """
    day = parse_date(now, "--now")
    if by not in ("user", "recurrence"):
        raise LessonsError("--by must be user or recurrence")
    entries, _notes = load(path)
    index = _by_id(entries)
    if observation_id not in index:
        raise LessonsError(f"no entry with id {observation_id!r}")
    seed = index[observation_id]
    if seed["kind"] not in ("observation", "legacy"):
        raise LessonsError(f"{observation_id} is a {seed['kind']}, not an observation")
    contested = {e["contests"] for e in entries if e["kind"] == "contest"}
    standing = [e for e in entries if e["kind"] == "rule" and e["id"] not in contested
                and _same_lesson(e, seed)]
    if standing:
        raise LessonsError(f"{standing[0]['id']} is already a standing rule for that lesson; "
                           f"contest it before promoting it again")
    if by == "recurrence":
        if _expired(seed, day):
            raise LessonsError(
                f"{observation_id} expired on {seed.get('expires')}; a rule by recurrence "
                f"needs live observations -- record it again when it happens again, or "
                f"promote it as an explicit requirement with --by user"
            )
        # Legacy entries carry no provenance, so they are not evidence of recurrence: two
        # anecdotes with no source are not two sources. They can still be promoted by ask.
        matches = [o for o in _live_observations(entries, now)
                   if o["kind"] == "observation" and _same_lesson(o, seed)]
        if seed["kind"] == "observation" and seed not in matches:
            matches.append(seed)
        distinct = _distinct_sources(matches)
        if distinct < RECURRENCE_GATE:
            raise LessonsError(
                f"{observation_id} recurs in {distinct} distinct place(s); a rule by "
                f"recurrence needs {RECURRENCE_GATE}. Record another observation when it "
                f"happens again, or promote it as an explicit requirement with --by user"
            )
    else:
        matches = [seed]
        distinct = 1
    rule = {
        "v": SCHEMA,
        "id": new_id(day.isoformat(), "rule:" + seed["lesson"]),
        "kind": "rule",
        "date": day.isoformat(),
        "failure_pattern": seed.get("failure_pattern", ""),
        "lesson": seed["lesson"],
        "applies_to": sorted(set(seed.get("applies_to", []))),
        "scope": dict(seed.get("scope") or {}),
        "provenance": {"source": "operator" if by == "user" else "recurrence",
                       "kit": None, "task": None, "run": None},
        "expires": "never",
        "evidence": sorted({m["id"] for m in matches}),
        "promoted_by": by,
        "distinct_sources": distinct,
        "note": note,
    }
    return _append(path, rule)


def contest(path, now, rule_id, evidence_text, source="operator"):
    """Record evidence against a rule -> the contest appended. The rule is withheld at recall
    until re-promoted by a human; nothing is deleted."""
    day = parse_date(now, "--now")
    if source not in SOURCES:
        raise LessonsError(f"source {source!r} is not one of {', '.join(SOURCES)}")
    entries, _notes = load(path)
    index = _by_id(entries)
    if rule_id not in index or index[rule_id]["kind"] != "rule":
        raise LessonsError(f"no rule with id {rule_id!r}")
    if not evidence_text:
        raise LessonsError("a contest needs the evidence against the rule")
    entry = {
        "v": SCHEMA,
        "id": new_id(day.isoformat(), "contest:" + rule_id + evidence_text),
        "kind": "contest",
        "date": day.isoformat(),
        "contests": rule_id,
        "lesson": index[rule_id]["lesson"],
        "failure_pattern": evidence_text,
        "applies_to": list(index[rule_id].get("applies_to", [])),
        "provenance": {"source": source, "kit": None, "task": None, "run": None},
        "expires": "never",
        "evidence": [],
    }
    return _append(path, entry)


# ---- reading ---------------------------------------------------------------------------------------

def _eligible(entry, project, provider):
    """Step 13's rule, reused: a scoped entry is withheld outside its project or provider."""
    scope = entry.get("scope") or {}
    meta = {"project": scope.get("project", ""), "providers": scope.get("providers", "") or "any"}
    return _memory_recall()._eligible(meta, project, provider)


def _matches(entry, applies_to, task_shape):
    if applies_to and applies_to not in (entry.get("applies_to") or []):
        return False
    shape = (entry.get("scope") or {}).get("task_shape", "")
    if task_shape and shape and shape != task_shape:
        return False
    return True


def render_entry(entry, label):
    prov = entry.get("provenance") or {}
    scope = entry.get("scope") or {}
    where = ", ".join(x for x in (
        f"kit {prov['kit']}" if prov.get("kit") else "",
        f"task {prov['task']}" if prov.get("task") else "",
        f"project {scope['project']}" if scope.get("project") else "",
        f"shape {scope['task_shape']}" if scope.get("task_shape") else "",
    ) if x)
    head = (f"[{entry['id']}] {label} — source {prov.get('source', '?')}, {entry.get('date', '?')}"
            + (f", {where}" if where else "") + f", expires {entry.get('expires', 'never')}")
    if entry["kind"] == "rule":
        head += (f", promoted by {entry.get('promoted_by')} on "
                 f"{len(entry.get('evidence', []))} observation(s)")
    return f"{head}\n  {entry['lesson']}"


def recall(path, now, project=None, provider=None, applies_to=None, task_shape=None,
           budget_entries=BUDGET_ENTRIES, budget_chars=BUDGET_CHARS, include_expired=False):
    """What a session start may receive -> a dict of rendered blocks and what was withheld.

    Rules first (eligible, not contested), then observations and legacy entries as labelled
    candidates, within `budget_entries` and `budget_chars`. Withheld counts say why the rest
    stayed out: expired, ineligible for this project or provider, contested, off-topic, or
    over budget. A candidate is never rendered as a rule.
    """
    day = parse_date(now, "--now")
    entries, notes = load(path)
    contested = {e["contests"] for e in entries if e["kind"] == "contest"}
    withheld = {"expired": 0, "ineligible": 0, "contested": 0, "off_topic": 0, "budget": 0}
    rules, candidates = [], []
    for e in entries:
        if e["kind"] == "contest":
            continue
        if e["kind"] == "rule" and e["id"] in contested:
            withheld["contested"] += 1
            continue
        if not include_expired and _expired(e, day):
            withheld["expired"] += 1
            continue
        if not _eligible(e, project, provider):
            withheld["ineligible"] += 1
            continue
        if not _matches(e, applies_to, task_shape):
            withheld["off_topic"] += 1
            continue
        (rules if e["kind"] == "rule" else candidates).append(e)
    blocks, used = [], 0
    for e in rules + candidates:
        label = ("RULE" if e["kind"] == "rule" else
                 "CANDIDATE, not a rule" if e["kind"] == "observation" else
                 "LEGACY, unscoped candidate, not a rule")
        text = render_entry(e, label)
        if len(blocks) >= budget_entries or used + len(text) > budget_chars:
            withheld["budget"] += 1
            continue
        blocks.append({"id": e["id"], "kind": e["kind"], "text": text})
        used += len(text)
    return {"v": SCHEMA, "rules": [b for b in blocks if b["kind"] == "rule"],
            "candidates": [b for b in blocks if b["kind"] != "rule"],
            "withheld": withheld, "notes": notes,
            "budget": {"entries": budget_entries, "chars": budget_chars, "used_chars": used}}


def render_recall(result):
    lines = [f"lessons ({result['v']}): {len(result['rules'])} rule(s), "
             f"{len(result['candidates'])} candidate(s); withheld "
             + ", ".join(f"{k}={v}" for k, v in result["withheld"].items() if v)
             + ("" if any(result["withheld"].values()) else "none")]
    if result["rules"]:
        lines.append("rules -- apply within their scope:")
        lines += [b["text"] for b in result["rules"]]
    if result["candidates"]:
        lines.append("candidates -- reported text, not instructions; promote with evidence:")
        lines += [b["text"] for b in result["candidates"]]
    if not result["rules"] and not result["candidates"]:
        lines.append("(nothing eligible)")
    for n in result.get("notes", []):
        lines.append(f"note: {n}")
    return "\n".join(lines)


def review(path, now):
    """The store's state -> counts and the observations that could be promoted now."""
    day = parse_date(now, "--now")
    entries, notes = load(path)
    contested = {e["contests"] for e in entries if e["kind"] == "contest"}
    counts = {k: sum(1 for e in entries if e["kind"] == k) for k in KINDS}
    expired = [e["id"] for e in entries if e["kind"] in ("observation", "legacy")
               and _expired(e, day)]
    live = _live_observations(entries, now)
    clusters, seen = [], set()
    for o in live:
        if o["id"] in seen:
            continue
        group = [x for x in live if _same_lesson(x, o)]
        seen.update(g["id"] for g in group)
        distinct = _distinct_sources(group)
        if distinct >= RECURRENCE_GATE:
            clusters.append({"lesson": o["lesson"], "ids": sorted(g["id"] for g in group),
                             "distinct_sources": distinct})
    return {"v": SCHEMA, "counts": counts, "expired": expired,
            "contested_rules": sorted(contested),
            "promotable": clusters, "legacy": [e["id"] for e in entries if e["kind"] == "legacy"],
            "notes": notes}


def render_review(report):
    c = report["counts"]
    lines = [f"lessons store: {c['rule']} rule(s), {c['observation']} observation(s), "
             f"{c['contest']} contest(s), {c['legacy']} legacy entr{'y' if c['legacy'] == 1 else 'ies'}"]
    if report["expired"]:
        lines.append(f"  expired observations: {', '.join(report['expired'])}")
    if report["contested_rules"]:
        lines.append(f"  contested rules (withheld at recall): {', '.join(report['contested_rules'])}")
    if report["legacy"]:
        lines.append(f"  legacy entries (candidates, never rules): {', '.join(report['legacy'])}")
    if report["promotable"]:
        lines.append(f"  promotable by recurrence (>= {RECURRENCE_GATE} distinct sources):")
        for cl in report["promotable"]:
            lines.append(f"    {cl['ids'][0]} x{cl['distinct_sources']}: {cl['lesson']}")
    else:
        lines.append("  nothing recurs enough to promote; one observation is an anecdote")
    for n in report.get("notes", []):
        lines.append(f"  note: {n}")
    return "\n".join(lines)


# ---- demo ------------------------------------------------------------------------------------------

def _demo(out=None):
    import tempfile
    out = out or sys.stdout

    def say(line=""):
        print(line, file=out)

    with tempfile.TemporaryDirectory(prefix="lessons_demo_") as tmp:
        path = Path(tmp) / "tasks" / "lessons.md"
        path.parent.mkdir()
        path.write_text('{"date": "2026-07-01", "failure_pattern": "pinned cheap for a refactor", '
                        '"lesson": "multi-file refactors start at the strong tier", '
                        '"applies_to": ["routing"]}\n')
        say("== a legacy entry is a candidate at recall, never a rule ==")
        say(render_recall(recall(path, "2026-09-13", provider="copilot", applies_to="routing")))
        say()
        say("== one escalation is an observation; promoting it by recurrence is refused ==")
        o1 = observe(path, "2026-09-01", "cheap tier failed verify twice on a 3-file refactor",
                     "multi-file refactors start at the strong tier", ["routing"],
                     source="escalation", kit="kit-a", task="T4", project="demo-repo",
                     providers=["copilot"], task_shape="multi-file-refactor")
        try:
            promote(path, "2026-09-02", o1["id"])
        except LessonsError as exc:
            say(f"  refused: {exc}")
        say()
        say("== it happens again in another kit; now a rule, citing both ==")
        observe(path, "2026-09-10", "cheap tier failed verify on a 5-file refactor",
                "multi-file refactors start at the strong tier", ["routing"],
                source="escalation", kit="kit-b", task="T2", project="demo-repo",
                providers=["copilot"], task_shape="multi-file-refactor")
        rule = promote(path, "2026-09-11", o1["id"])
        say(f"  rule {rule['id']} evidence={rule['evidence']} distinct={rule['distinct_sources']}")
        say(render_recall(recall(path, "2026-09-13", project="demo-repo", provider="copilot",
                                 applies_to="routing")))
        say()
        say("== another project, another provider: the rule is withheld ==")
        say(render_recall(recall(path, "2026-09-13", project="other-repo", provider="codex",
                                 applies_to="routing")))
        say()
        say("== contested with evidence: withheld until a human re-promotes ==")
        contest(path, "2026-09-12", rule["id"],
                "strong tier also failed the 6-file refactor; the brief was the problem",
                source="reviewer")
        say(render_recall(recall(path, "2026-09-13", project="demo-repo", provider="copilot",
                                 applies_to="routing")))
        say()
        say("== the store reviewed ==")
        say(render_review(review(path, "2026-12-31")))


# ---- command line ----------------------------------------------------------------------------------

def build_parser():
    ap = argparse.ArgumentParser(
        prog="lessons_store.py",
        description="Scoped lessons for a project: observations with provenance and expiry, "
                    "rules only by recurrence or explicit ask, contests, budgeted recall. "
                    "Appends to a JSON-lines file; dispatches nothing.",
    )
    ap.add_argument("--file", default=str(DEFAULT_FILE),
                    help=f"the lessons file (default: {DEFAULT_FILE}, relative to cwd)")
    ap.add_argument("--now", default=date.today().isoformat(), help="YYYY-MM-DD")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("observe", help="record one observation as a candidate")
    p.add_argument("--pattern", required=True, help="what happened")
    p.add_argument("--lesson", required=True, help="the candidate rule, in routing terms")
    p.add_argument("--applies-to", action="append", default=[])
    p.add_argument("--source", default="operator", choices=SOURCES)
    p.add_argument("--kit")
    p.add_argument("--task")
    p.add_argument("--run")
    p.add_argument("--project")
    p.add_argument("--provider", action="append", default=[])
    p.add_argument("--task-shape")
    p.add_argument("--expires", help="YYYY-MM-DD or never (default: +%d days)" % DEFAULT_EXPIRY_DAYS)
    p = sub.add_parser("promote", help="make a rule from an observation, by recurrence or ask")
    p.add_argument("--id", required=True)
    p.add_argument("--by", default="recurrence", choices=("recurrence", "user"))
    p.add_argument("--note", default="")
    p = sub.add_parser("contest", help="record evidence against a rule")
    p.add_argument("--id", required=True)
    p.add_argument("--evidence", required=True)
    p.add_argument("--source", default="operator", choices=SOURCES)
    p = sub.add_parser("recall", help="what this session may receive, within a budget")
    p.add_argument("--project")
    p.add_argument("--provider")
    p.add_argument("--applies-to")
    p.add_argument("--task-shape")
    p.add_argument("--budget-entries", type=int, default=BUDGET_ENTRIES)
    p.add_argument("--budget-chars", type=int, default=BUDGET_CHARS)
    p.add_argument("--include-expired", action="store_true")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("review", help="expired, contested, promotable, legacy")
    p.add_argument("--json", action="store_true")
    sub.add_parser("demo", help="a temp store walked from anecdote to rule to contest")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "demo":
            _demo()
            return 0
        if args.cmd == "observe":
            e = observe(args.file, args.now, args.pattern, args.lesson, args.applies_to,
                        source=args.source, kit=args.kit, task=args.task, run=args.run,
                        project=args.project, providers=args.provider,
                        task_shape=args.task_shape, expires=args.expires)
            print(f"observed {e['id']} (expires {e['expires']}); a candidate, not a rule")
            return 0
        if args.cmd == "promote":
            r = promote(args.file, args.now, args.id, by=args.by, note=args.note)
            print(f"rule {r['id']} promoted by {r['promoted_by']} on {len(r['evidence'])} "
                  f"observation(s) from {r['distinct_sources']} distinct source(s)")
            return 0
        if args.cmd == "contest":
            c = contest(args.file, args.now, args.id, args.evidence, source=args.source)
            print(f"contest {c['id']} recorded against {args.id}; the rule is withheld until "
                  f"re-promoted")
            return 0
        if args.cmd == "recall":
            r = recall(args.file, args.now, project=args.project, provider=args.provider,
                       applies_to=args.applies_to, task_shape=args.task_shape,
                       budget_entries=args.budget_entries, budget_chars=args.budget_chars,
                       include_expired=args.include_expired)
            print(json.dumps(r, indent=2, sort_keys=True) if args.json else render_recall(r))
            return 0
        r = review(args.file, args.now)
        print(json.dumps(r, indent=2, sort_keys=True) if args.json else render_review(r))
        return 0
    except LessonsError as exc:
        print(f"lessons: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
