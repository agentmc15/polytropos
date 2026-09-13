#!/usr/bin/env python3
"""The Cursor adapter: the smallest useful native slice on the shared runtime (step 23).

WHAT CURSOR IS, FROM ITS OWN DOCUMENTATION (read 2026-09-13; every product fact here cites
one of these pages and nothing is inferred from another page):

  https://cursor.com/docs/cli/headless             -- the binary is `agent`; headless is
      `agent -p --output-format text|json|stream-json [--force|--yolo] "<prompt>"`; auth is
      `CURSOR_API_KEY` or `--api-key`.
  https://cursor.com/docs/cli/reference/parameters -- `-v/--version`, `--model <model>`,
      `--list-models` and `agent models`, `--mode plan|ask`, `--workspace <path>`,
      `--trust` (headless workspace trust), `--sandbox enabled|disabled`, `--resume`,
      `--continue`, `about --format json` (version, system, account), `worker start` (a
      private cloud worker).
  https://cursor.com/docs/skills                    -- project skills at
      `.cursor/skills/<name>/SKILL.md` (Agent Skills standard: `name`, `description`); also
      discovered: `.agents/skills/`, and the LEGACY paths `.claude/skills/` and
      `.codex/skills/`, walked recursively.
  https://cursor.com/docs/subagents                 -- project subagents at
      `.cursor/agents/*.md` with `name`, `description`, `model` (`inherit` or an id),
      `readonly`, `is_background`; also discovered: `.claude/agents/` and `.codex/agents/`;
      they run "in the editor, CLI, and Cloud Agents"; cloud subagents launch via `/in-cloud`.

THREE MODES, REPORTED SEPARATELY. The IDE agent, the local CLI, and background/cloud agents
are three products. This adapter drives the CLI. Files it installs (skills, subagents) are
consumed by all three, which is a fact about the files, not a claim that this adapter drives
the IDE or a cloud worker: `modes_report` says `cli: implemented`, `ide: files only`,
`cloud: files only`, and none of the three is `verified` because nothing here is run live.

IDENTITY BEFORE TRUST. The binary is called `agent`, a name anything could have. Before a
dispatch this adapter asks it `--version` and, failing that, `about --format json`, and
treats it as Cursor only when the answer says so (`IDENTITY_TOKEN`). Unknown is refused: a
required guarantee (we are about to hand this process `--force` over a workspace) fails
closed. Account fields the `about` payload may carry are never kept -- only a version string.

WHAT IS UNKNOWN STAYS UNKNOWN. The CLI documents no usage or cost output; `usage_report` says
so and reads nothing else (Cursor's `state.vscdb` is an undocumented SQLite store this
repository does not open, see `bin/journal_sources.py`). The observed model is taken only
from a `model` field the CLI's own JSON output carries, never from the prompt or a price
list; `data/pricing.cursor.json` records no model ids or rates and says why.

AMBIENT COMPATIBILITY. Cursor also loads `.claude/agents`, `.claude/skills`, and
`.codex/skills`. A polytropos kit writes its agents under `.claude/agents/<slug>-*.md`, and
those prompts name `/polytropos:execute` and other harnesses' commands. `diagnose_ambient`
names every such file so a Cursor session does not act on another harness's instructions.

Every process is started through `bin/proc_runner.py`; every install write goes through
`bin/safe_paths.py` under the project root; nothing here scrapes an editor database or
automates a browser.
"""

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

BINARY = "agent"
IDENTITY_TOKEN = "cursor"
IDENTITIES = ("cursor", "unknown", "absent")
PROBE_TIMEOUT_SECONDS = 30
DISPATCH_TIMEOUT_SECONDS = 3600
OUTPUT_FORMAT = "json"
READ_ONLY_MODE = "ask"
PLACEHOLDER = "{{POLYTROPOS_ROOT}}"
PRICING_FILE = "data/pricing.cursor.json"

DOCS = {
    "headless": "https://cursor.com/docs/cli/headless",
    "parameters": "https://cursor.com/docs/cli/reference/parameters",
    "skills": "https://cursor.com/docs/skills",
    "subagents": "https://cursor.com/docs/subagents",
}

#: The three products, each answered on its own. `product` is what the documentation says;
#: `implemented` is what this repository does; `verified` is what someone has run here.
MODES = {
    "cli": {"product": "supported", "implemented": "supported", "verified": "unknown",
            "source": DOCS["headless"],
            "note": "driven by this adapter through `agent -p`; never run live from the "
                    "repository, so verified stays unknown"},
    "ide": {"product": "supported", "implemented": "files-only", "verified": "unknown",
            "source": DOCS["subagents"],
            "note": "the IDE agent reads the same `.cursor/skills` and `.cursor/agents` files "
                    "this adapter installs; no operation here drives the IDE"},
    "cloud": {"product": "supported", "implemented": "files-only", "verified": "unknown",
              "source": DOCS["subagents"],
              "note": "cloud subagents (`/in-cloud`) and private workers (`agent worker`) read "
                      "project-level files only; no operation here launches or drives one"},
}

#: Flags an operator may not pass through `--extra-arg`: they would replace the identity,
#: the mode, the model, or the session this adapter chose and recorded.
BLOCKED_EXTRA_ARGS = ("--api-key", "--force", "-f", "--yolo", "--mode", "--plan", "--model",
                      "--resume", "--continue", "--workspace", "-w", "--worktree",
                      "--worktree-base", "--print", "-p", "--output-format")

#: Tokens that mark a file as carrying another harness's commands.
OTHER_HARNESS_TOKENS = ("claude -p", "copilot --agent", "codex exec", "/polytropos:",
                        "${CLAUDE_PLUGIN_ROOT}", "claude_execute.py", "copilot_execute.py",
                        "codex_execute.py")

#: Where Cursor discovers skills and subagents in a project, and what each is.
AMBIENT_GLOBS = (
    (".claude/agents/*.md", "subagent"),
    (".codex/agents/*.md", "subagent"),
    (".claude/skills/*/SKILL.md", "skill"),
    (".codex/skills/*/SKILL.md", "skill"),
    (".agents/skills/*/SKILL.md", "skill"),
)
AMBIENT_MAX_FILES = 200

BUNDLE_DIR = REPO_ROOT / "cursor"
#: (bundle-relative source, project-relative destination)
BUNDLE = (
    ("skills/polytropos-execute/SKILL.md", ".cursor/skills/polytropos-execute/SKILL.md"),
    ("agents/polytropos-implementer.md", ".cursor/agents/polytropos-implementer.md"),
    ("agents/polytropos-verifier.md", ".cursor/agents/polytropos-verifier.md"),
)
MANIFEST_REL = ".cursor/polytropos/install-manifest.json"
MANIFEST_VERSION = 1
BACKUP_SUFFIX = ".polytropos-bak"
INSTALL_STATES = ("install", "up-to-date", "managed-update", "adopt-update", "unmanaged")


class IdentityError(RuntimeError):
    """The executable could not be shown to be Cursor; nothing is dispatched to it."""


class InstallConflict(RuntimeError):
    """A destination this installer does not own differs from what it would write."""


# ---- siblings ---------------------------------------------------------------------------------------

_SIBLINGS = {}


def _sibling(name):
    if name not in _SIBLINGS:
        path = Path(__file__).resolve().with_name(f"{name}.py")
        spec = importlib.util.spec_from_file_location(f"polytropos_{name}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SIBLINGS[name] = module
    return _SIBLINGS[name]


def _ha():
    return _sibling("harness_adapter")


def _pr():
    return _sibling("proc_runner")


def _sp():
    return _sibling("safe_paths")


# ---- identity ---------------------------------------------------------------------------------------

def _run(argv, cwd, timeout, runner=None):
    """One read-only probe through the process runner, or an injected runner -> result dict."""
    if runner is not None:
        return runner(argv)
    pr = _pr()
    return pr.run(argv, cwd=cwd or Path.cwd(), timeout=timeout, name="cursor probe",
                  env=pr.dispatch_env("cursor"))


def identify(cursor_bin=BINARY, cwd=None, runner=None):
    """Is `cursor_bin` Cursor? -> a dict with `identity` in `IDENTITIES`.

    `--version` first; `about --format json` when that says nothing. The answer is `cursor`
    only when the output names it. The `about` payload can carry account fields; only a
    version string is kept from it, and the evidence recorded is the bounded first line.
    """
    resolved = shutil.which(cursor_bin) or (str(Path(cursor_bin)) if Path(cursor_bin).exists()
                                            else None)
    report = {"binary": cursor_bin, "resolved": resolved, "identity": "absent", "version": None,
              "evidence": "", "reason": ""}
    if resolved is None:
        report["reason"] = f"{cursor_bin!r} is not on PATH and is not a file"
        return report
    first = _run([resolved, "--version"], cwd, PROBE_TIMEOUT_SECONDS, runner)
    text = (first.get("stdout") or "") + "\n" + (first.get("stderr") or "")
    line = text.strip().splitlines()[0][:120] if text.strip() else ""
    if IDENTITY_TOKEN in text.lower():
        report.update(identity="cursor", version=line, evidence=line,
                      reason="`--version` names Cursor")
        return report
    second = _run([resolved, "about", "--format", "json"], cwd, PROBE_TIMEOUT_SECONDS, runner)
    out = second.get("stdout") or ""
    try:
        payload = json.loads(out) if out.strip() else None
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        blob = json.dumps(payload).lower()
        if IDENTITY_TOKEN in blob:
            version = payload.get("version") if isinstance(payload.get("version"), str) else None
            report.update(identity="cursor", version=version, evidence=f"about: version={version}",
                          reason="`about --format json` names Cursor")
            return report
    report.update(identity="unknown", evidence=line,
                  reason=f"neither `--version` ({line or 'no output'}) nor `about --format json` "
                         f"names Cursor; refusing to treat {cursor_bin!r} as Cursor")
    return report


def require_cursor(report):
    """Fail closed: dispatch only to a binary that identified itself."""
    if report.get("identity") != "cursor":
        raise IdentityError(
            f"cursor identity is {report.get('identity')}: {report.get('reason')}. Point "
            f"--cursor-bin at the Cursor CLI (installed by https://cursor.com/install)"
        )
    return report


def list_models(cursor_bin=BINARY, cwd=None, runner=None):
    """The host's own model list (`agent models`) -> ids, or unknown with the reason.

    A read of account data over the network; run only when asked. Nothing is inferred
    from a price list: an empty answer is `unknown`, not a default roster.
    """
    resolved = shutil.which(cursor_bin) or cursor_bin
    result = _run([resolved, "models"], cwd, PROBE_TIMEOUT_SECONDS, runner)
    out = (result.get("stdout") or "").strip()
    if result.get("rc") != 0 or not out:
        return {"models": [], "source": "agent models", "available": False,
                "reason": f"`agent models` exit {result.get('rc')}: {(result.get('stderr') or out or 'no output')[:160]}"}
    models = []
    try:
        payload = json.loads(out)
        if isinstance(payload, list):
            models = [str(m.get("id") if isinstance(m, dict) else m) for m in payload]
    except ValueError:
        for line in out.splitlines():
            token = line.strip().split()[0] if line.strip() else ""
            if token and not token.startswith(("#", "-")):
                models.append(token.rstrip(":,"))
    return {"models": models[:200], "source": "agent models", "available": bool(models),
            "reason": "" if models else "no model id could be read from the output"}


def usage_report():
    """What this adapter knows about spend: nothing, and it says so."""
    return {
        "available": False,
        "billed_usd": None,
        "reason": ("Cursor's CLI documents no usage or cost output, and its `state.vscdb` is "
                   "an undocumented SQLite store this repository does not open; usage and "
                   "model identity are unknown unless the CLI's own JSON output names them"),
        "pricing_file": PRICING_FILE,
    }


def modes_report():
    return {mode: dict(spec) for mode, spec in MODES.items()}


# ---- the adapter ------------------------------------------------------------------------------------

class CursorAdapter:
    """`harness_adapter.Adapter` for Cursor's CLI. Built lazily as a subclass so the sibling
    module is loaded once; see `adapter()`."""


def adapter():
    """The Cursor adapter instance (a `harness_adapter.Adapter` subclass)."""
    ha = _ha()

    class _CursorAdapter(ha.Adapter):
        name = "cursor"
        client_mode = "cli (agent -p)"
        pricing_file = PRICING_FILE

        def capabilities(self):
            return ha.registry_capabilities("cursor")

        def build_dispatch(self, task, model_id=None, prompt="", cursor_bin=BINARY,
                           workspace=None, read_only=False, extra_args=()):
            return build_dispatch(task, model_id=model_id, prompt=prompt,
                                  cursor_bin=cursor_bin, workspace=workspace,
                                  read_only=read_only, extra_args=extra_args)

        def normalize_result(self, raw):
            base = super().normalize_result(raw)
            base.update(parse_output(raw.get("stdout", "")))
            return base

    return _CursorAdapter()


def _validate_extra_args(extra_args):
    for arg in extra_args:
        head = arg.split("=", 1)[0]
        if head in BLOCKED_EXTRA_ARGS:
            raise ValueError(f"extra dispatch option {arg!r} would override what this adapter "
                             f"chose and recorded (identity, mode, model, workspace, session)")


def build_dispatch(task, model_id=None, prompt="", cursor_bin=BINARY, workspace=None,
                   read_only=False, extra_args=()):
    """The `agent -p` argv for one task -> a list, never a shell string.

    Headless print mode with JSON output and `--trust` (the documented headless trust
    flag); `--workspace` pins the directory; `--model` only when a model was chosen;
    `--mode ask` for a read-only dispatch (review, verification), `--force` otherwise so an
    implementer may write. The prompt is the last argument, and it names the task: a
    prompt-only CLI has nowhere else to carry the id, so one is prefixed when the prompt does
    not already mention it (a driver's id preamble does). Nothing here is verified live: the
    flags are the documentation's, cited in the module docstring.
    """
    extra_args = list(extra_args)
    _validate_extra_args(extra_args)
    argv = [cursor_bin, "-p", "--output-format", OUTPUT_FORMAT, "--trust"]
    if workspace:
        argv += ["--workspace", str(workspace)]
    if model_id:
        argv += ["--model", model_id]
    argv += ["--mode", READ_ONLY_MODE] if read_only else ["--force"]
    argv += extra_args
    text = prompt if prompt else task.get("brief", "")
    task_id = task.get("id")
    if task_id and task_id not in text:
        text = f"[task={task_id}]\n\n{text}"
    argv.append(text)
    return argv


def parse_output(stdout):
    """What the CLI's JSON output says, and nothing it does not.

    `--output-format json` is documented; its schema is not. A top-level object is kept
    (bounded); a string `model` field in it is the only thing accepted as an observed model,
    and only because the host wrote it. Anything else is `None`, not a guess.
    """
    text = (stdout or "").strip()
    parsed = None
    if text:
        try:
            parsed = json.loads(text)
        except ValueError:
            # stream-json or text: the last JSON object line, if any, is what a reader would
            # have; otherwise nothing is parsed.
            for line in reversed(text.splitlines()):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        parsed = json.loads(line)
                        break
                    except ValueError:
                        continue
    observed_model = None
    result_text = None
    if isinstance(parsed, dict):
        if isinstance(parsed.get("model"), str):
            observed_model = parsed["model"]
        for key in ("result", "text", "response", "content"):
            if isinstance(parsed.get(key), str):
                result_text = parsed[key][:2000]
                break
    return {"parsed": isinstance(parsed, dict), "observed_model": observed_model,
            "result_text": result_text, "usage": None}


# ---- ambient compatibility ----------------------------------------------------------------------------

def diagnose_ambient(project_root):
    """Files Cursor would discover that carry another harness's commands -> findings."""
    root = Path(project_root)
    sp = _sp()
    findings, scanned = [], 0
    for pattern, kind in AMBIENT_GLOBS:
        for path in sorted(root.glob(pattern)):
            if scanned >= AMBIENT_MAX_FILES:
                findings.append({"path": None, "kind": "limit", "tokens": [],
                                 "note": f"stopped after {AMBIENT_MAX_FILES} files"})
                return findings
            scanned += 1
            rel = path.relative_to(root).as_posix()
            try:
                data = sp.confined_read_bytes(root, rel, what="ambient scan", missing_ok=True)
            except sp.SafePathError as exc:
                findings.append({"path": rel, "kind": kind, "tokens": [],
                                 "note": f"not read: {exc}"})
                continue
            text = (data or b"").decode("utf-8", "replace")
            hits = [t for t in OTHER_HARNESS_TOKENS if t in text]
            if hits:
                findings.append({
                    "path": rel, "kind": kind, "tokens": hits,
                    "note": (f"Cursor discovers this {kind} from a legacy location; it names "
                             f"another harness's commands ({', '.join(hits)}) and would be "
                             f"acted on as if they were Cursor's"),
                })
    return findings


# ---- install, ownership-aware ------------------------------------------------------------------------

def _sha(data):
    return hashlib.sha256(data).hexdigest()


def bundle_sources(repo_root=REPO_ROOT):
    """The bundle's files with the root placeholder resolved -> {dest_rel: bytes}."""
    out = {}
    for src_rel, dest_rel in BUNDLE:
        source = Path(repo_root) / "cursor" / src_rel
        if not source.is_file():
            raise FileNotFoundError(f"bundle file missing: {source}")
        text = source.read_text(encoding="utf-8").replace(PLACEHOLDER, str(Path(repo_root).resolve()))
        out[dest_rel] = text.encode("utf-8")
    return out


def _load_manifest(project_root):
    sp = _sp()
    try:
        raw = sp.confined_read_bytes(project_root, MANIFEST_REL, what="cursor manifest",
                                     missing_ok=True)
    except sp.SafePathError:
        return {}
    if not raw:
        return {}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except ValueError:
        return {}
    if not isinstance(payload, dict) or payload.get("version") != MANIFEST_VERSION:
        return {}
    return payload.get("files") or {}


def plan_install(project_root, repo_root=REPO_ROOT, adopt_unmanaged=False):
    """Classify every destination before a byte is written -> a plan.

      install         absent
      up-to-date      identical bytes already there
      managed-update  present, and the manifest says this installer wrote what is there
      unmanaged       present, differs, and not ours -- preserved unless `adopt_unmanaged`
      adopt-update    unmanaged, but adoption was asked for; a backup is kept
    """
    root = Path(project_root)
    sp = _sp()
    owned = _load_manifest(root)
    actions = []
    for dest_rel, desired in bundle_sources(repo_root).items():
        current = None
        try:
            current = sp.confined_read_bytes(root, dest_rel, what="cursor install",
                                             missing_ok=True)
        except sp.SafePathError as exc:
            actions.append({"destination": dest_rel, "state": "unmanaged", "write": False,
                            "reason": f"refusing to read through {exc}", "backup": None})
            continue
        if current is None:
            state, reason = "install", "absent"
        elif current == desired:
            state, reason = "up-to-date", "identical"
        elif owned.get(dest_rel) == _sha(current):
            state, reason = "managed-update", "this installer wrote the current bytes"
        elif adopt_unmanaged:
            state, reason = "adopt-update", "differs and not ours; adopting with a backup"
        else:
            state, reason = "unmanaged", "differs and not ours; preserved"
        actions.append({
            "destination": dest_rel, "state": state, "reason": reason,
            "write": state in ("install", "managed-update", "adopt-update"),
            "backup": dest_rel + BACKUP_SUFFIX if state == "adopt-update" else None,
            "desired_sha256": _sha(desired), "desired": desired,
        })
    return {"project_root": str(root), "manifest": MANIFEST_REL, "actions": actions,
            "conflicts": [a["destination"] for a in actions if a["state"] == "unmanaged"]}


def apply_install(plan):
    """Write what the plan allows, through the confined writer, then the manifest.

    A conflict in the plan means nothing is written at all; the operator resolves it or
    passes `--adopt-existing`. Files this run wrote are removed if a later write fails;
    backups are kept.
    """
    if plan["conflicts"]:
        raise InstallConflict(
            "preserved and NOT written: " + ", ".join(plan["conflicts"])
            + " -- rerun with --adopt-existing to overwrite them, keeping a backup of each"
        )
    root = Path(plan["project_root"])
    sp = _sp()
    written = []
    try:
        for action in plan["actions"]:
            if not action["write"]:
                continue
            if action["backup"]:
                current = sp.confined_read_bytes(root, action["destination"],
                                                 what="cursor backup", missing_ok=True)
                if current is not None:
                    sp.confined_write_bytes(root, action["backup"], current,
                                            what="cursor backup", create_parents=True)
            sp.confined_write_bytes(root, action["destination"], action["desired"],
                                    what="cursor install", mode=0o644, create_parents=True)
            written.append(action["destination"])
        manifest = {
            "version": MANIFEST_VERSION,
            "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "files": {a["destination"]: a["desired_sha256"] for a in plan["actions"]},
        }
        sp.confined_write_bytes(root, MANIFEST_REL,
                                (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
                                what="cursor manifest", mode=0o644, create_parents=True)
    except Exception:
        for rel in written:
            try:
                sp.confined_unlink(root, rel, what="cursor rollback", missing_ok=True)
            except sp.SafePathError:
                pass
        raise
    return written


def render_plan(plan, applied=None):
    lines = [f"cursor install plan for {plan['project_root']} (manifest {plan['manifest']}):"]
    for a in plan["actions"]:
        lines.append(f"  {a['state']:<14} {a['destination']} -- {a['reason']}")
    if plan["conflicts"]:
        lines.append(f"  {len(plan['conflicts'])} destination(s) preserved and NOT written; "
                     f"rerun with --adopt-existing to overwrite them, keeping a backup of each")
    if applied is not None:
        lines.append(f"  wrote {len(applied)} file(s)")
    return "\n".join(lines)


def smoke_command(project_root, cursor_bin=BINARY):
    """The optional live smoke, as text. Documented, never run by this repository: it would
    contact Cursor with the user's credentials and could spend."""
    return (f"{cursor_bin} -p --trust --workspace {Path(project_root).resolve()} "
            f"--output-format json --mode ask \"Reply with the single word ready\"")


def doctor(project_root, cursor_bin=BINARY, repo_root=REPO_ROOT, runner=None):
    """Identity, modes, install state, ambient files, and what stays unknown -> a report."""
    root = Path(project_root)
    identity = identify(cursor_bin, cwd=root, runner=runner)
    try:
        plan = plan_install(root, repo_root=repo_root)
        install = [{k: a[k] for k in ("destination", "state", "reason")} for a in plan["actions"]]
    except FileNotFoundError as exc:
        install = [{"destination": None, "state": "error", "reason": str(exc)}]
    return {
        "binary": identity,
        "modes": modes_report(),
        "install": install,
        "ambient": diagnose_ambient(root),
        "usage": usage_report(),
        "smoke": {"command": smoke_command(root, cursor_bin),
                  "note": "documented, not run; it contacts Cursor and may spend"},
        "docs": dict(DOCS),
    }


def render_doctor(report):
    b = report["binary"]
    lines = [f"cursor: binary {b['binary']} -> {b['resolved'] or 'absent'}; identity "
             f"{b['identity']}" + (f" ({b['version']})" if b.get("version") else "")
             + f" -- {b['reason']}"]
    lines.append("modes (each on its own):")
    for mode, spec in report["modes"].items():
        lines.append(f"  {mode:<5} product={spec['product']} implemented={spec['implemented']} "
                     f"verified={spec['verified']} -- {spec['note']}")
    lines.append("install:")
    for a in report["install"]:
        lines.append(f"  {a['state']:<14} {a['destination']} -- {a['reason']}")
    if report["ambient"]:
        lines.append("ambient files Cursor discovers that carry another harness's commands:")
        for f in report["ambient"]:
            lines.append(f"  {f['path']} ({f['kind']}): {', '.join(f['tokens']) or f['note']}")
    else:
        lines.append("ambient: no legacy-location file names another harness's commands")
    lines.append(f"usage: unknown -- {report['usage']['reason']}")
    lines.append(f"smoke (not run): {report['smoke']['command']}")
    return "\n".join(lines)


# ---- demo -------------------------------------------------------------------------------------------------

def _demo(out=None):
    out = out or sys.stdout

    def say(line=""):
        print(line, file=out)

    def fake_cursor(argv):
        if argv[-1] == "--version":
            return {"rc": 0, "stdout": "cursor-agent 0.0.0-demo\n", "stderr": "", "outcome": "ok"}
        if argv[1:] == ["models"]:
            return {"rc": 0, "stdout": "demo-model-a\ndemo-model-b\n", "stderr": "", "outcome": "ok"}
        return {"rc": 0, "stdout": json.dumps({"model": "demo-model-a", "result": "done"}),
                "stderr": "", "outcome": "ok"}

    def fake_other(argv):
        if argv[-1] == "--version":
            return {"rc": 0, "stdout": "some-other-agent 9.9\n", "stderr": "", "outcome": "ok"}
        return {"rc": 1, "stdout": "", "stderr": "unknown command", "outcome": "failed"}

    with tempfile.TemporaryDirectory(prefix="cursor_demo_") as tmp:
        root = Path(tmp)
        (root / "demo-agent").write_text("#!/bin/sh\nexit 0\n")
        (root / "demo-agent").chmod(0o755)
        bin_path = str(root / "demo-agent")
        say("== identity: a binary that names Cursor, and one that does not ==")
        ok = identify(bin_path, runner=fake_cursor)
        say(f"  {ok['identity']}: {ok['reason']} ({ok['version']})")
        bad = identify(bin_path, runner=fake_other)
        say(f"  {bad['identity']}: {bad['reason']}")
        try:
            require_cursor(bad)
        except IdentityError as exc:
            say(f"  refused: {str(exc)[:110]}...")
        say()
        say("== the dispatch argv, write and read-only ==")
        task = {"id": "T1", "brief": "do the thing"}
        say("  " + " ".join(build_dispatch(task, model_id="demo-model-a", prompt="do it",
                                           cursor_bin="agent", workspace=root)))
        say("  " + " ".join(build_dispatch(task, prompt="review it", cursor_bin="agent",
                                           workspace=root, read_only=True)))
        say()
        say("== output parsed, usage unknown ==")
        say(f"  {parse_output(json.dumps({'model': 'demo-model-a', 'result': 'ok'}))}")
        say(f"  usage: {usage_report()['reason'][:90]}...")
        say()
        say("== install into a project: absent, identical, unmanaged, adopted ==")
        proj = root / "project"
        proj.mkdir()
        plan = plan_install(proj)
        say(render_plan(plan, apply_install(plan)))
        say(render_plan(plan_install(proj)))
        target = proj / ".cursor" / "agents" / "polytropos-verifier.md"
        target.write_text(target.read_text() + "\n# local edit\n")
        plan = plan_install(proj)
        say(render_plan(plan))
        plan = plan_install(proj, adopt_unmanaged=True)
        say(render_plan(plan, apply_install(plan)))
        say(f"  backup kept: {(target.with_name(target.name + BACKUP_SUFFIX)).exists()}")
        say()
        say("== ambient: a kit agent Cursor would load as a subagent ==")
        (proj / ".claude" / "agents").mkdir(parents=True)
        (proj / ".claude" / "agents" / "demo-implementer.md").write_text(
            "---\nname: demo-implementer\n---\nRun /polytropos:execute demo then claude -p ...\n")
        for f in diagnose_ambient(proj):
            say(f"  {f['path']} ({f['kind']}): {', '.join(f['tokens'])}")
        say()
        say("== modes, each on its own ==")
        for mode, spec in modes_report().items():
            say(f"  {mode}: product={spec['product']} implemented={spec['implemented']} "
                f"verified={spec['verified']}")
        say(f"  smoke (not run): {smoke_command(proj)}")


# ---- command line -----------------------------------------------------------------------------------------

def build_parser():
    ap = argparse.ArgumentParser(
        prog="cursor_adapter.py",
        description="The Cursor CLI adapter: identity probe, model list, project-scoped "
                    "install with ownership, ambient-file diagnosis, and the documented live "
                    "smoke (printed, never run).",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe", help="is --cursor-bin Cursor? read-only")
    p.add_argument("--cursor-bin", default=BINARY)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("models", help="the host's model list (`agent models`; network)")
    p.add_argument("--cursor-bin", default=BINARY)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("install", help="write the native bundle into a project's .cursor/")
    p.add_argument("--project", required=True)
    p.add_argument("--adopt-existing", action="store_true",
                   help="overwrite an unmanaged destination, keeping a .polytropos-bak")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("doctor", help="identity, modes, install state, ambient files")
    p.add_argument("--project", default=".")
    p.add_argument("--cursor-bin", default=BINARY)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("smoke", help="print the optional live smoke command; never runs it")
    p.add_argument("--project", default=".")
    p.add_argument("--cursor-bin", default=BINARY)
    sub.add_parser("demo", help="fake binaries and a temp project; spends nothing")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.cmd == "demo":
        _demo()
        return 0
    if args.cmd == "probe":
        report = identify(args.cursor_bin)
        print(json.dumps(report, indent=2, sort_keys=True) if args.json else
              f"cursor identity: {report['identity']} -- {report['reason']}")
        return 0 if report["identity"] == "cursor" else 3
    if args.cmd == "models":
        report = list_models(args.cursor_bin)
        print(json.dumps(report, indent=2, sort_keys=True) if args.json else
              ("\n".join(report["models"]) if report["models"] else
               f"models unknown: {report['reason']}"))
        return 0 if report["available"] else 3
    if args.cmd == "install":
        try:
            plan = plan_install(args.project, adopt_unmanaged=args.adopt_existing)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if args.dry_run:
            print(json.dumps({k: v for k, v in plan.items() if k != "actions"} | {
                "actions": [{k: a[k] for k in ("destination", "state", "reason")}
                            for a in plan["actions"]]}, indent=2) if args.json else
                  render_plan(plan))
            return 2 if plan["conflicts"] else 0
        try:
            written = apply_install(plan)
        except InstallConflict as exc:
            print(render_plan(plan), file=sys.stderr)
            print(str(exc), file=sys.stderr)
            return 2
        print(render_plan(plan, written))
        return 0
    if args.cmd == "smoke":
        print(smoke_command(args.project, args.cursor_bin))
        print("(documented, not run: it contacts Cursor with your credentials and may spend)")
        return 0
    report = doctor(args.project, args.cursor_bin)
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else render_doctor(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
