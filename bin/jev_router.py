#!/usr/bin/env python3
"""Jev as a ROUTER for the route experiment: per task, ask TypeSafe's Jev which route to run.

Jev is a decision API, not a code writer. For each experiment task this asks one request with
four questions over a FIXED route menu (arm ids from the experiment): the route most likely to
solve the task well (`route_quality`), the cheapest route likely to solve it (`route_economy`),
the task's difficulty, and whether a review gate would help. The menu describes each route only
by its a-priori shape, models, pricing tiers and pricing-profile estimate -- never a measured
result, so nothing the experiment observed can leak into a pick.

  prepare  build one V1 DecisionRequest per task, redact the free text with bin/redact.py, and
           write the exact canonical bytes plus a manifest whose sha a human approves. Spends
           nothing; opens no network.
  show     print the exact bytes that would be sent, for review.
  send     the ONLY outbound path: requires --approve equal to the manifest sha, a call cap and a
           timeout. One HTTPS POST per task, never retried, never redirected. The credential is
           read at send time from $TYPESAFE_API_KEY or an env file and is never printed, logged or
           stored. A call that starts writes an O_EXCL marker first, so an unknown-outcome call
           is never silently replayed.
  picks    the picks per objective, plus the `--only`/`--extend-arms` arguments that run them
           live through bin/route_experiment.py.
  score    replay: score each router's picks against a run's recorded trials, beside every
           static menu route, a uniform-random router, and the hindsight oracle.
  demo     the whole path offline with a stub transport and synthetic answers.

Usage is reported as Jev's own token counts; no pricing file covers Jev, so no dollar figure
is ever derived. Jev has no routing authority here: its picks are experiment arms, nothing
else (docs/JEV-ACCESS-CONTRACT.md).
"""

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENT_DIR = REPO_ROOT / "experiments" / "route-arms-v2"
STUDY_VERSION = "polytropos.jev-router/1"
KEY_NAME = "TYPESAFE_API_KEY"
DEFAULT_ENV_FILE = Path(".config") / "polytropos" / ".env"
STATE_CHUNK = 2000
MAX_RESPONSE_BYTES = 256 * 1024
OBJECTIVES = ("route_quality", "route_economy")
_MODS = {}


def _sibling(name):
    if name not in _MODS:
        spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parent
                                                      / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _MODS[name] = module
    return _MODS[name]


def _rx():
    return _sibling("route_experiment")


def _jev():
    return _sibling("jev_decision_provider")


def _dc():
    return _jev()._contract()


def _sp():
    return _sibling("safe_paths")


class RouterError(RuntimeError):
    pass


def _sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8")).hexdigest()


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------------------------
# Building the requests


def route_text(exp, pricing, arm_id):
    """One route's a-priori description: shape, models and tiers, rework, profile estimate."""
    rx = _rx()
    arm = exp["arms"][arm_id]
    models = pricing["models"]

    def who(stage):
        m = models[stage["model"]]
        return f"{m.get('display', stage['model'])} ({m.get('tier', '?')} tier) at {stage['effort']} effort"

    st = arm["stages"]
    rework = exp.get("rework") or {}
    if arm["shape"] == "one-shot":
        body = f"one-shot: {who(st['solo'])} writes the whole change alone in one session."
    elif arm["shape"] == "reviewed":
        body = (f"reviewed one-shot: {who(st['solo'])} writes the change, then {who(st['reviewer'])}"
                f" reviews it; a rejection sends findings back for up to "
                f"{rework.get('after_reviewer_reject', 0)} rework round(s).")
    elif arm["shape"] == "best-of":
        n = (arm.get("variant") or {}).get("n", rx.BEST_OF_DEFAULT_N)
        body = (f"best-of-{n}: {who(st['solo'])} writes the change {n} times independently; "
                "the project's own tests and each attempt's tests run against the others pick "
                "the one kept.")
    elif arm["shape"] == "escalate":
        gate = (f"; if they pass, {who(st['verifier'])} verifies it" if "verifier" in st else "")
        body = (f"escalate-on-fail: {who(st['solo'])} writes the change, the project's tests "
                f"run on it{gate}; only on a failure does {who(st['escalation'])} take over "
                "the working tree once.")
    else:
        parts = [f"planner {who(st['planner'])} writes a plan",
                 f"test author {who(st['test_author'])} writes tests first",
                 f"implementer {who(st['implementer'])} implements",
                 f"verifier {who(st['verifier'])} runs and judges the tests"]
        if "reviewer" in st:
            parts.append(f"reviewer {who(st['reviewer'])} gates the final diff")
        rounds = f"up to {rework.get('after_verifier_fail', 0)} rework round(s) after a failed verification"
        if "reviewer" in st:
            rounds += f" and {rework.get('after_reviewer_reject', 0)} after a rejected review"
        body = "pipeline: " + "; ".join(parts) + f"; {rounds}."
    variant = arm.get("variant") or {}
    notes = {"spec-hardener": "the planner writes a numbered requirements contract, not steps",
             "spec": "the test author works from the task text alone, never the plan",
             "traceable": "gates must tie every negative verdict to a failing test or an "
                          "unmet requirement"}
    extra = [notes[v] for v in variant.values() if v in notes]
    if extra:
        body += " Variant: " + "; ".join(extra) + "."
    est = rx.arm_estimate(exp, pricing, arm_id)
    span = (f"{est['min']:.1f}" if abs(est["max"] - est["min"]) < 0.05
            else f"{est['min']:.1f}-{est['max']:.1f}")
    return (f"Route {arm_id}, {body} A-priori cost estimate {span} AI credits per attempt "
            f"(pricing-profile token estimate; real spend varies with effort and cache use).")


def _questions(route_texts):
    return [
        {"id": "route_quality", "version": "v1", "kind": "choice",
         "question": "Which one of these routes is most likely to fully solve the described "
                     "coding task -- passing its hidden correctness and regression tests with "
                     "simple, well-tested code -- regardless of cost?",
         "rubric": dict(route_texts), "outcomes": list(route_texts), "abstention": "forbidden",
         "dependencies": [], "sensitivity": "public"},
        {"id": "route_economy", "version": "v1", "kind": "choice",
         "question": "Which one of these routes is the cheapest in AI credits that is still "
                     "likely to fully solve the described coding task and pass its hidden "
                     "correctness and regression tests?",
         "rubric": dict(route_texts), "outcomes": list(route_texts), "abstention": "forbidden",
         "dependencies": [], "sensitivity": "public"},
        {"id": "task_difficulty", "version": "v1", "kind": "ordinal",
         "question": "How difficult is the described coding task for an AI coding agent to "
                     "complete correctly on its first attempt?",
         "rubric": {"trivial": "A one-line or mechanical edit with no design decisions.",
                    "easy": "A small, local change following an obvious existing pattern.",
                    "moderate": "Several coordinated edits with a few edge cases to get right.",
                    "hard": "Subtle behaviour, many edge cases, or behaviour that must be "
                            "preserved exactly while restructuring.",
                    "very_hard": "Deep cross-cutting reasoning where most capable agents would "
                                 "miss something on a first attempt."},
         "outcomes": ["trivial", "easy", "moderate", "hard", "very_hard"],
         "abstention": "forbidden", "dependencies": [], "sensitivity": "public"},
        {"id": "needs_review", "version": "v1", "kind": "boolean",
         "question": "Would a separate expert review gate materially raise the chance that the "
                     "described coding change ends up correct?",
         "rubric": {"false": "A capable implementer working alone is about as likely to get it "
                             "right; review adds cost without much benefit.",
                    "true": "The change has pitfalls an independent reviewer would likely "
                            "catch, so a review gate is worth its cost."},
         "outcomes": ["false", "true"], "abstention": "forbidden", "dependencies": [],
         "sensitivity": "public"},
    ]


def task_state(task):
    """-> (flat state, redaction report). Free text is redacted BEFORE it is chunked."""
    redact = _sibling("redact")
    prompt = redact.redact(task["prompt_text"], limit=None)
    title = redact.redact(task.get("title") or task["id"], limit=None)
    text = prompt["text"]
    chunks = [text[i:i + STATE_CHUNK] for i in range(0, len(text), STATE_CHUNK)] or [""]
    state = {"task_id": task["short"], "task_title": title["text"],
             "task_kind": str(task.get("kind") or "change"),
             "setting": "Each route attempts the task in a fresh sandbox of one Python 3 "
                        "stdlib-only repository; hidden tests and a regression suite grade the "
                        "result. Costs are in GitHub Copilot AI credits.",
             "task_prompt_parts": len(chunks)}
    for index, chunk in enumerate(chunks, 1):
        state[f"task_prompt_{index}"] = chunk
    kinds = {}
    for found in (prompt["redactions"], title["redactions"]):
        for kind, count in found.items():
            kinds[kind] = kinds.get(kind, 0) + count
    return state, {"redactions": kinds, "prompt_chars": prompt["original_length"]}


def build_request(study, exp, pricing, task, menu):
    al, kc, dc = _sibling("attempt_ledger"), _sibling("kit_contract"), _dc()
    state, red = task_state(task)
    questions = _questions({arm: route_text(exp, pricing, arm) for arm in menu})
    payload = {
        "v": dc.CONTRACT_VERSION, "correlation_id": f"{study}-{task['short']}",
        "run": study, "task": task["id"], "attempt": None, "intended_use": "advice",
        "task_ref": al.make_ref(task["id"], sha=task["digests"]["prompt"],
                                version=kc.CONTRACT_VERSION),
        "acceptance_ref": al.make_ref(f"{task['id']}-oracle", sha=task["digests"]["oracle"],
                                      version=kc.CONTRACT_VERSION),
        "state": state, "state_sha": dc.state_digest(state),
        "alternatives": list(menu), "questions": questions,
        "questions_sha": dc.questions_digest([dc.parse_question(q) for q in questions]),
        "eligibility": {"project": "polytropos", "providers": ["jev"],
                        "privacy": "vendor-eligible"},
        "deadline_s": 30,
        "resource_policy": {"operation_scope": "consult", "call_ceiling": 1,
                            "repair_ceiling": 0},
        "admission_ref": al.make_ref(f"{study}-user-approval", version=kc.CONTRACT_VERSION),
    }
    return dc.parse_request(payload), payload, red


def manifest_sha(manifest):
    core = {"study": manifest["study"], "jev_model": manifest["jev_model"],
            "endpoint": manifest["endpoint"],
            "payloads": {t: v["sha256"] for t, v in sorted(manifest["tasks"].items())}}
    return _sha(json.dumps(core, sort_keys=True, separators=(",", ":")))


class Study:
    """One router study's private records under `<routeruns>/jev-router/<study>/`."""

    def __init__(self, store_dir, study):
        self.study = _sp().validate_id(study, "study id")
        self.root = Path(store_dir) / "jev-router" / self.study

    def write(self, rel, data, create=False):
        _sibling("runtime_data").ensure_private(self.root)
        if isinstance(data, (dict, list)):
            data = json.dumps(data, indent=2, sort_keys=True) + "\n"
        data = data.encode("utf-8") if isinstance(data, str) else data
        fn = _sp().confined_create_bytes if create else _sp().confined_replace
        fn(self.root, rel, data, what="jev-router record")

    def read(self, rel):
        if not self.root.is_dir():
            return None
        raw = _sp().confined_read_bytes(self.root, rel, what="jev-router record", missing_ok=True)
        return None if raw is None else raw

    def read_json(self, rel):
        raw = self.read(rel)
        return None if raw is None else json.loads(raw.decode("utf-8"))

    def manifest(self):
        manifest = self.read_json("manifest.json")
        if manifest is None:
            raise RouterError(f"no study {self.study!r} under {self.root.parent}; run prepare")
        return manifest


def _load_exp(exp_dir, pricing):
    rx = _rx()
    exp, digest = rx.load_experiment(Path(exp_dir), pricing)
    rx.merge_extensions(exp, [a for a in exp["extensions"] if a not in exp["arms"]])
    return exp, digest


def prepare(study, exp_dir, store_dir, menu, jev_model, tasks=None, pricing=None):
    rx, jev = _rx(), _jev()
    pricing = pricing or rx.load_pricing()
    exp, digest = _load_exp(exp_dir, pricing)
    menu = list(dict.fromkeys(menu))
    unknown = [a for a in menu if a not in exp["arms"]]
    if unknown:
        raise RouterError(f"menu names arms the experiment does not define: {unknown}")
    if not 2 <= len(menu) <= _dc().MAX_OUTCOMES:
        raise RouterError(f"the menu needs 2..{_dc().MAX_OUTCOMES} routes, got {len(menu)}")
    st = Study(store_dir, study)
    if st.read("manifest.json") is not None and st.read_json("manifest.json").get("sent"):
        raise RouterError(f"study {study!r} already has sent calls; prepare a new study id")
    manifest = {"version": STUDY_VERSION, "study": study, "jev_model": jev_model,
                "endpoint": jev.DOCUMENTED_ENDPOINT, "experiment": str(exp_dir),
                "preregistration": digest, "menu": menu, "prepared": _now(), "tasks": {}}
    for task_id in tasks or exp["tasks"]:
        task = exp["task_defs"][task_id]
        request, payload, red = build_request(study, exp, pricing, task, menu)
        body = jev.serialize_payload(request, model=jev_model, endpoint=jev.DOCUMENTED_ENDPOINT)
        if len(body) > _dc().MAX_PAYLOAD_CHARS:
            raise RouterError(f"{task_id}: {len(body)} bytes exceeds the local payload ceiling")
        st.write(f"payloads/{task['short']}.json", body)
        st.write(f"requests/{task['short']}.json", payload)
        manifest["tasks"][task_id] = {"short": task["short"], "bytes": len(body),
                                      "sha256": _sha(body), **red}
    manifest["approval_sha"] = manifest_sha(manifest)
    st.write("manifest.json", manifest)
    return manifest


# ---------------------------------------------------------------------------------------------
# The one outbound path


def load_key(env_file=None, environ=None):
    """The credential VALUE, from the environment first, then a KEY=value env file. Raises
    without echoing anything but the key NAME and the file path."""
    environ = os.environ if environ is None else environ
    if environ.get(KEY_NAME):
        return environ[KEY_NAME]
    path = Path(env_file) if env_file else Path(environ.get("HOME", "/")) / DEFAULT_ENV_FILE
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        raise RouterError(f"{KEY_NAME} is not set and {path} is unreadable") from None
    for line in lines:
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        name, sep, value = line.partition("=")
        if sep and name.strip() == KEY_NAME:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            if value:
                return value
    raise RouterError(f"{KEY_NAME} is not set in the environment or in {path}")


def https_transport(url, body, key, timeout):
    """One POST, no redirect, bounded read. -> (http status, parsed JSON or None, error kind)."""
    import urllib.error
    import urllib.request

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    if not url.startswith("https://"):
        raise RouterError("refusing a non-HTTPS endpoint")
    opener = urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            status = response.status
    except urllib.error.HTTPError as exc:
        return exc.code, None, {401: "unauthorized", 422: "validation", 429: "rate-limited",
                                529: "overloaded"}.get(exc.code, "http-error")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, None, ("timeout" if "timed out" in str(exc).lower() else "transport")
    if len(raw) > MAX_RESPONSE_BYTES:
        return status, None, "response-too-large"
    try:
        return status, json.loads(raw.decode("utf-8")), None
    except (UnicodeDecodeError, ValueError):
        return status, None, "unparseable"


_ANSWER_FIELDS = {"noul": ("type", "noul"),
                  "choice": ("type", "choice", "probabilities", "confidence"),
                  "score": ("type", "score", "legend", "probabilities", "confidence")}


def project_response(data):
    """Keep only the documented fields -> (projection, names of ignored fields). Values outside
    the documented shape are dropped by NAME, never echoed."""
    ignored = sorted(k for k in data if k not in ("model", "answers", "usage"))
    answers = {}
    for qid, answer in (data.get("answers") or {}).items():
        if not isinstance(answer, dict):
            continue
        keep = _ANSWER_FIELDS.get(answer.get("type"), ("type",))
        ignored += sorted(f"answers.{qid}.{k}" for k in answer if k not in keep)
        answers[qid] = {k: answer[k] for k in keep if k in answer}
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    return ({"model": data.get("model"), "answers": answers,
             "usage": {k: usage.get(k) for k in ("input_tokens", "output_tokens")}}, ignored)


def interpret(request, projected, jev_model):
    """-> {pick per question, distributions, contract conformance}. The strict V1 mapper is
    authoritative; if it refuses, Jev's own `choice` field is used and labelled non-conformant."""
    jev, dc = _jev(), _dc()
    out = {"conformant": True, "contract_error": None, "answers": {}}
    try:
        mapped = jev.map_response(request, projected, model=jev_model,
                                  endpoint=jev.DOCUMENTED_ENDPOINT)
        for qid, a in mapped["answers"].items():
            out["answers"][qid.split("@")[0]] = {"pick": a["outcome"], "raw": a["raw"],
                                                 "confidence": a["vendor_confidence"]}
    except dc.ContractError as exc:
        out.update(conformant=False, contract_error=getattr(exc, "code", "invalid"))
        for qid, a in projected["answers"].items():
            name = qid.split("@")[0]
            pick = a.get("choice") if a.get("type") == "choice" else (
                a.get("noul") if a.get("type") == "noul" else a.get("score"))
            out["answers"][name] = {"pick": pick, "raw": a.get("probabilities"),
                                    "confidence": a.get("confidence")}
    return out


def send(study, store_dir, approve, max_calls, timeout, env_file=None, transport=None,
         key_loader=None, out=sys.stdout):
    st = Study(store_dir, study)
    manifest = st.manifest()
    if approve != manifest["approval_sha"] or manifest_sha(manifest) != approve:
        raise RouterError("--approve does not match this study's manifest sha; review with "
                          "`show` and approve the sha `prepare` printed")
    todo = []
    for task_id, entry in sorted(manifest["tasks"].items()):
        body = st.read(f"payloads/{entry['short']}.json")
        if body is None or _sha(body) != entry["sha256"]:
            raise RouterError(f"{task_id}: payload bytes differ from the approved manifest")
        if st.read(f"calls/{entry['short']}.json") is None:
            todo.append((task_id, entry, body))
    if len(todo) > max_calls:
        raise RouterError(f"{len(todo)} calls pending but --max-calls is {max_calls}; nothing sent")
    if not todo:
        print("every task already has a call record; nothing sent", file=out)
        return manifest
    key = (key_loader or load_key)(env_file)
    transport = transport or https_transport
    dc = _dc()
    for task_id, entry, body in todo:
        request = dc.parse_request(st.read_json(f"requests/{entry['short']}.json"))
        rel = f"calls/{entry['short']}.json"
        st.write(rel, {"task": task_id, "status": "started", "started": _now(),
                       "payload_sha256": entry["sha256"]}, create=True)
        t0 = time.monotonic()
        status, data, error = transport(manifest["endpoint"], body, key, timeout)
        record = {"task": task_id, "payload_sha256": entry["sha256"], "http_status": status,
                  "duration_s": round(time.monotonic() - t0, 3), "finished": _now(),
                  "requested_model": manifest["jev_model"]}
        if error or not isinstance(data, dict):
            record.update(status="failed", error=error or "not-an-object")
        else:
            projected, ignored = project_response(data)
            record.update(status="ok", observed_model=projected["model"],
                          usage=projected["usage"], ignored_fields=ignored,
                          answers=projected["answers"],
                          interpreted=interpret(request, projected, manifest["jev_model"]))
        st.write(rel, record)
        print(f"  {entry['short']}: {record['status']}"
              + (f" ({record.get('error')})" if record["status"] == "failed" else
                 f" model={record['observed_model']} tokens in/out="
                 f"{record['usage'].get('input_tokens')}/{record['usage'].get('output_tokens')}"),
              file=out)
    manifest["sent"] = True
    st.write("manifest.json", manifest)
    return manifest


# ---------------------------------------------------------------------------------------------
# Picks and scoring


def picks(study, store_dir):
    st = Study(store_dir, study)
    manifest = st.manifest()
    rows = {}
    for task_id, entry in sorted(manifest["tasks"].items()):
        call = st.read_json(f"calls/{entry['short']}.json") or {}
        answers = ((call.get("interpreted") or {}).get("answers") or {})
        rows[task_id] = {
            "short": entry["short"], "status": call.get("status", "unsent"),
            "conformant": (call.get("interpreted") or {}).get("conformant"),
            **{obj: (answers.get(obj) or {}).get("pick") for obj in OBJECTIVES},
            **{f"{obj}_confidence": (answers.get(obj) or {}).get("confidence")
               for obj in OBJECTIVES},
            "difficulty": (answers.get("task_difficulty") or {}).get("pick"),
            "needs_review": (answers.get("needs_review") or {}).get("pick"),
            "usage": call.get("usage")}
    return manifest, rows


def live_args(manifest, rows, repeat=1):
    trials, arms = [], set()
    for row in rows.values():
        for obj in OBJECTIVES:
            arm = row.get(obj)
            if arm:
                trials.append(f"{row['short']}-{arm}-r{repeat}")
                arms.add(arm)
    return sorted(set(trials)), sorted(arms)


def run_cells(exp_dir, store_dir, run_id, arms, pricing=None):
    """{(task, arm): {n, solve, qs, aic, wall_s}} from a run's graded trials, judge quality left
    out for every arm (extension arms are never judged)."""
    rx = _rx()
    pricing = pricing or rx.load_pricing()
    exp, digest = rx.load_experiment(Path(exp_dir), pricing)
    ex = rx.Experiment(exp, digest, pricing, Path(store_dir), run_id)
    manifest = ex.read_json("run.json")
    if manifest is None:
        raise RouterError(f"no run {run_id!r} under {store_dir}")
    ex.activate(manifest)
    present = sorted({t["arm"] for t in ex.records("trials")} & set(arms) & set(ex.exp["arms"]))
    if not present:
        return {}
    report = rx.build_report(ex, arms=present, drop=("quality",), view="extended")
    cells = {}
    for r in report["rows"]:
        cells.setdefault((r["task"], r["arm"]), []).append(r)
    return {k: {"n": len(v), "solve": sum(1 for r in v if r["solved"]) / len(v),
                "qs": sum(r["qs"] for r in v) / len(v), "aic": sum(r["aic"] for r in v) / len(v),
                "wall_s": sum(r["wall_s"] or 0 for r in v) / len(v)}
            for k, v in cells.items()}


def _router_score(choice, cells, tasks):
    """choice: {task: arm}. -> summary over the tasks whose pick has data."""
    got = [cells[(t, choice[t])] for t in tasks if choice.get(t) and (t, choice[t]) in cells]
    if not got:
        return {"covered": 0, "tasks": len(tasks)}
    return {"covered": len(got), "tasks": len(tasks),
            "qs": sum(c["qs"] for c in got) / len(got),
            "solve": sum(c["solve"] for c in got) / len(got),
            "aic_per_task": sum(c["aic"] for c in got) / len(got),
            "aic_total": sum(c["aic"] for c in got),
            "wall_s": sum(c["wall_s"] for c in got) / len(got)}


def score(manifest, rows, cells, baseline_cells=None):
    """Router picks scored on `cells`; static routes, random and hindsight oracles on
    `baseline_cells` (default: the same cells -- the replay case)."""
    base = cells if baseline_cells is None else baseline_cells
    tasks = sorted(rows)
    menu = manifest["menu"]
    full = [t for t in tasks if all((t, a) in base for a in menu)]
    out = {"tasks": tasks, "complete_tasks": full, "routers": {}, "static": {}, "oracle": {}}
    for obj in OBJECTIVES:
        out["routers"][f"jev-{obj.split('_')[1]}"] = _router_score(
            {t: rows[t].get(obj) for t in tasks}, cells, tasks)
    for arm in menu:
        out["static"][arm] = _router_score({t: arm for t in tasks}, base, tasks)
    def best_quality(t):
        return max(menu, key=lambda a: (base[(t, a)]["qs"], -base[(t, a)]["aic"]))
    def cheapest_solver(t):
        top = max(base[(t, a)]["solve"] for a in menu)
        return min((a for a in menu if base[(t, a)]["solve"] == top),
                   key=lambda a: base[(t, a)]["aic"])
    if full:
        out["oracle"]["hindsight-quality"] = dict(
            _router_score({t: best_quality(t) for t in full}, base, full),
            picks={t: best_quality(t) for t in full})
        out["oracle"]["hindsight-economy"] = dict(
            _router_score({t: cheapest_solver(t) for t in full}, base, full),
            picks={t: cheapest_solver(t) for t in full})
        rand = [base[(t, a)] for t in full for a in menu]
        out["oracle"]["uniform-random"] = {
            "covered": len(full), "tasks": len(tasks),
            "qs": sum(c["qs"] for c in rand) / len(rand),
            "solve": sum(c["solve"] for c in rand) / len(rand),
            "aic_per_task": sum(c["aic"] for c in rand) / len(rand)}
    tokens = [r["usage"] or {} for r in rows.values()]
    out["jev_usage"] = {"input_tokens": sum(u.get("input_tokens") or 0 for u in tokens),
                        "output_tokens": sum(u.get("output_tokens") or 0 for u in tokens),
                        "calls": sum(1 for r in rows.values() if r["status"] == "ok"),
                        "basis": "Jev-reported tokens; no pricing file covers Jev, so no "
                                 "dollar or credit figure is derived"}
    return out


def render_score(result, out=sys.stdout):
    def line(name, s):
        if not s.get("covered"):
            return f"  {name:<20} no data"
        return (f"  {name:<20} QS {s['qs']:5.1f}  solve {100 * s['solve']:5.1f}%  "
                f"AIC/task {s['aic_per_task']:7.2f}  covered {s['covered']}/{s['tasks']}")
    print("Jev routers:", file=out)
    for k, s in result["routers"].items():
        print(line(k, s), file=out)
    print("Baselines (always the same route):", file=out)
    for k, s in sorted(result["static"].items(), key=lambda kv: -(kv[1].get("qs") or -1)):
        print(line(k, s), file=out)
    if result["oracle"]:
        print("Reference routers:", file=out)
        for k, s in result["oracle"].items():
            print(line(k, s), file=out)
    else:
        print("Reference routers: need every menu route measured on a task", file=out)
    u = result["jev_usage"]
    print(f"Jev usage: {u['calls']} call(s), {u['input_tokens']} input / {u['output_tokens']} "
          f"output tokens ({u['basis']})", file=out)


# ---------------------------------------------------------------------------------------------
# Demo and CLI


def _stub_transport(manifest_menu, cheap):
    def transport(url, body, key, timeout):
        assert key == "demo-not-a-key"
        q = json.loads(body.decode("utf-8"))["questions"]
        def choice(pick):
            rest = (1 - 0.6) / (len(manifest_menu) - 1)
            probs = {a: (0.6 if a == pick else rest) for a in manifest_menu}
            return {"type": "choice", "choice": pick, "probabilities": probs,
                    "confidence": 0.5}
        legend = {str(i): text for i, text in enumerate(q["task_difficulty@v1"]["criteria"])}
        probs = {"0": 0.0, "1": 0.2, "2": 0.6, "3": 0.2, "4": 0.0}
        return 200, {"model": "synthetic-jev", "id": "ignored-by-name",
                     "answers": {"route_quality@v1": choice(manifest_menu[0]),
                                 "route_economy@v1": choice(cheap),
                                 "task_difficulty@v1": {"type": "score", "legend": legend,
                                                        "probabilities": probs,
                                                        "score": 2.0, "confidence": 0.4},
                                 "needs_review@v1": {"type": "noul", "noul": 0.7}},
                     "usage": {"input_tokens": 3000, "output_tokens": 40}}, None
    return transport


def run_demo(out=sys.stdout):
    """Offline: prepare -> send through a stub -> picks -> score against synthetic cells."""
    rx = _rx()
    pricing = rx.load_pricing()
    exp, _ = _load_exp(EXPERIMENT_DIR, pricing)
    menu = sorted(exp["arms"], key=lambda a: int(a[1:]) if a[1:].isdigit() else 0)[:4]
    with tempfile.TemporaryDirectory() as tmp:
        m = prepare("demo", EXPERIMENT_DIR, tmp, menu, "synthetic-jev", pricing=pricing)
        print(f"prepared {len(m['tasks'])} payloads; approval sha {m['approval_sha'][:16]}...",
              file=out)
        send("demo", tmp, m["approval_sha"], len(m["tasks"]), 10,
             transport=_stub_transport(menu, menu[-1]), key_loader=lambda _f: "demo-not-a-key",
             out=out)
        manifest, rows = picks("demo", tmp)
        cells = {(t, a): {"n": 1, "solve": 1.0 if i % 2 == 0 else 0.0, "qs": 60 + 10 * i,
                          "aic": 5.0 * (i + 1), "wall_s": 100.0}
                 for t in rows for i, a in enumerate(menu)}
        render_score(score(manifest, rows, cells), out=out)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--experiment-dir", default=str(EXPERIMENT_DIR))
    parser.add_argument("--store-dir", help="route-experiment store (default: routeruns)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare", help="build and record the exact payloads; sends nothing")
    p.add_argument("--study", required=True)
    p.add_argument("--menu", required=True, help="comma-separated arm ids (2..16)")
    p.add_argument("--jev-model", required=True, help="pinned Jev model id")
    p.add_argument("--tasks", help="comma-separated task ids (default: all)")
    p = sub.add_parser("show", help="print the exact bytes that would be sent")
    p.add_argument("--study", required=True)
    p.add_argument("--task", help="one task id or short id (default: the manifest summary)")
    p = sub.add_parser("send", help="the one outbound path; needs --approve")
    p.add_argument("--study", required=True)
    p.add_argument("--approve", required=True, help="the manifest sha prepare printed")
    p.add_argument("--max-calls", type=int, required=True)
    p.add_argument("--timeout", type=float, default=10.0)
    p.add_argument("--env-file", help=f"KEY=value file holding {KEY_NAME}")
    p = sub.add_parser("picks", help="per-task picks and the live-run arguments")
    p.add_argument("--study", required=True)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("score", help="score the routers against a run's recorded trials")
    p.add_argument("--study", required=True)
    p.add_argument("--run", required=True, help="run whose trials score the Jev picks")
    p.add_argument("--baseline-run", help="run for static/oracle baselines (default: --run)")
    p.add_argument("--json", action="store_true")
    sub.add_parser("demo", help="offline: stub transport, synthetic answers")
    args = parser.parse_args(argv)
    store = Path(args.store_dir) if args.store_dir else _rx().default_store_dir()
    try:
        if args.cmd == "demo":
            return run_demo()
        if args.cmd == "prepare":
            m = prepare(args.study, args.experiment_dir, store, args.menu.split(","),
                        args.jev_model, tasks=args.tasks.split(",") if args.tasks else None)
            for task_id, e in m["tasks"].items():
                red = ", ".join(f"{k}:{v}" for k, v in sorted(e["redactions"].items())) or "none"
                print(f"  {task_id}: {e['bytes']} bytes sha256 {e['sha256'][:16]}... "
                      f"redactions {red}")
            print(f"menu: {','.join(m['menu'])}\nmodel: {m['jev_model']}  endpoint: "
                  f"{m['endpoint']}\napproval sha: {m['approval_sha']}")
            return 0
        st = Study(store, args.study)
        if args.cmd == "show":
            manifest = st.manifest()
            if not args.task:
                print(json.dumps({k: v for k, v in manifest.items()}, indent=2))
                return 0
            entry = next((e for t, e in manifest["tasks"].items()
                          if args.task in (t, e["short"])), None)
            if entry is None:
                raise RouterError(f"no task {args.task!r} in this study")
            sys.stdout.write(st.read(f"payloads/{entry['short']}.json").decode("utf-8") + "\n")
            return 0
        if args.cmd == "send":
            send(args.study, store, args.approve, args.max_calls, args.timeout,
                 env_file=args.env_file)
            return 0
        manifest, rows = picks(args.study, store)
        if args.cmd == "picks":
            trials, arms = live_args(manifest, rows)
            ext = [a for a in arms if a in (_load_exp(args.experiment_dir, None)[0]
                                             .get("extensions") or {})]
            if args.json:
                print(json.dumps({"rows": rows, "only": trials, "extend_arms": ext}, indent=2))
                return 0
            for task_id, r in rows.items():
                print(f"  {r['short']}: quality={r['route_quality']} economy={r['route_economy']}"
                      f" difficulty={r['difficulty']} review={r['needs_review']} "
                      f"[{r['status']}{'' if r['conformant'] in (True, None) else ', non-conformant'}]")
            print(f"--only {','.join(trials)}" + (f" --extend-arms {','.join(ext)}" if ext else ""))
            return 0
        cells = run_cells(args.experiment_dir, store, args.run, manifest["menu"])
        base = (run_cells(args.experiment_dir, store, args.baseline_run, manifest["menu"])
                if args.baseline_run else None)
        result = score(manifest, rows, cells, base)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            render_score(result)
        return 0
    except RouterError as exc:
        print(f"jev_router: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
