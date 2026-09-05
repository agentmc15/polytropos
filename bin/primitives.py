#!/usr/bin/env python3
"""Load, validate, and preview an aesop-schema TOML manifest (PLAN.md D2-D6, aesop-fold T4).

Read-only engine: it never writes a manifest — no TOML writer exists anywhere in this repo
(PLAN D3). Manifests are read with stdlib `tomllib`, no fallback import, Python floor 3.11.
It reads only `primitives/*.json` and the manifest path it is given.

`check` has no JSON-Schema library (none is stdlib), so it is a hand-written rule set whose
enums and patterns are read from the vendored `primitives/aesop.schema.v1.json` at call
time — never retyped as Python literals. A few rules aesop enforces in code, not its
schema, are pinned here too: the three loop hard-stops are never defaulted in silently
("stops"); the verify loop must be real ("verify-loop"); judge and primary must differ in
model family ("judge-family"); MCP env entries must be bare variable NAMES ("env-value");
names must be path-safe, mirroring aesop's `isSafeName` ("unsafe-name"); and the raw
manifest text is scanned for four secret shapes copied verbatim from aesop's doctor
("secret").

TOML dialect (pinned here — also the T6 conversion target): `version`, `harnesses`, and
`registries` are bare root scalars/arrays and MUST precede the first `[table]` header,
since a bare `key = value` after any header belongs to that table, not the root. Then
`[project]` and its dotted sub-tables; `[pathway]`; then `[primitives]` with its plain
array keys (`skills`, `agents`, `commands`, `hooks`, `mcp = []` / `loops = []` when empty)
written BEFORE any of `[primitives.instructions]`, `[[primitives.instructions.blocks]]`,
`[[primitives.mcp]]`, `[primitives.permissions]`, `[[primitives.loops]]` — a table cannot
be reopened, so a non-empty `mcp`/`loops` is populated only via its array-of-tables form.
Finally `[state]`. `agents` may hold inline tables, e.g.
`agents = [ "explorer", { name = "security-reviewer", model = "strong" } ]`.

Exit codes (PLAN D6): 0 ok · 1 usage/file-missing/parse-error · 2 findings (or unknown
`--harness`).
"""

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PRIMITIVES_DIR = REPO_ROOT / "primitives"

# aesop src/commands/init.ts TEST_PLACEHOLDER — the honest default doctor flags until fixed.
TEST_PLACEHOLDER = "TODO: set your test command"

# Bare env var NAME only — no "=", no braces, no leading digit.
ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# aesop src/commands/doctor.ts SECRET_PATTERNS, copied verbatim.
SECRET_PATTERNS = (
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "GitHub token"),
    (re.compile(r"sk-[A-Za-z0-9-]{20,}"), "API key (sk-...)"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key"),
    (
        re.compile(
            r"(?:api[_-]?key|secret|token|password)[\"']?\s*[:=]\s*[\"'](?!\$\{)[^\"'\s]{12,}[\"']",
            re.IGNORECASE,
        ),
        "literal credential",
    ),
)

class ManifestError(Exception):
    """Raised when a manifest cannot be located or parsed as TOML."""

def load_schema(path=PRIMITIVES_DIR / "aesop.schema.v1.json"):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def load_model(path=PRIMITIVES_DIR / "model.json"):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def load_matrix(path=PRIMITIVES_DIR / "harness-matrix.json"):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def _read_manifest_text(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        raise ManifestError(f"manifest not found: {path}")

def load_manifest(path):
    """Parse the TOML manifest at `path`. Raises ManifestError on a missing file or on
    malformed TOML (the tomllib error text is preserved in the message)."""
    raw_text = _read_manifest_text(path)
    try:
        return tomllib.loads(raw_text)
    except tomllib.TOMLDecodeError as e:
        raise ManifestError(str(e))

def _schema_get(schema, *path):
    """Walk a dotted/indexed path into the vendored schema dict. The one chokepoint every
    enum/pattern lookup goes through, so nothing here is ever retyped as a Python literal."""
    node = schema
    for key in path:
        node = node[key]
    return node

def _finding(code, message, at=""):
    return {"code": code, "message": message, "at": at}

def _ref_name(item):
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return item.get("name")
    return None

def _is_positive_int(v):
    """True int (never TOML's bool, a distinct type aesop and this validator both reject
    where an integer >= 1 is required) that is at least 1."""
    return not isinstance(v, bool) and isinstance(v, int) and v >= 1

def _check_instructions(instructions, schema):
    if not isinstance(instructions, dict):
        return []
    blocks = instructions.get("blocks")
    if not isinstance(blocks, list):
        return []
    pattern = re.compile(_schema_get(
        schema, "properties", "primitives", "properties", "instructions",
        "properties", "blocks", "items", "properties", "scope", "pattern",
    ))
    out = []
    for i, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        at = f"primitives.instructions.blocks[{i}]"
        scope = block.get("scope")
        if not isinstance(scope, str) or not pattern.match(scope):
            out.append(_finding("schema", f"{at}.scope is invalid: {scope!r}", f"{at}.scope"))
        content = block.get("content")
        if not isinstance(content, str):
            out.append(_finding("schema", f"{at}.content must be a string", f"{at}.content"))
    return out

def _agent_enum_findings(item, at, ref):
    """The one place primitiveRef and agentRef genuinely differ: agentRef tables may also
    carry model/effort, each checked against its own schema enum."""
    out = []
    for field in ("model", "effort"):
        value = item.get(field)
        enum = set(ref[field]["enum"])
        if value is not None and value not in enum:
            out.append(_finding("schema", f"{at}.{field} is not one of {sorted(enum)}: {value!r}", f"{at}.{field}"))
    return out

def _check_ref_list(items, at_prefix, schema, defs_key, per_table=None):
    """Shared oneOf[string-pattern | table-with-name] shape check for primitiveRef and
    agentRef lists (skills/commands/hooks/agents) — the two schema defs share this exact
    shape, differing only in their patterns and, for agents, extra per-table enum fields."""
    if not isinstance(items, list):
        return []
    str_pattern = re.compile(_schema_get(schema, "$defs", defs_key, "oneOf", 0, "pattern"))
    ref = _schema_get(schema, "$defs", defs_key, "oneOf", 1, "properties")
    name_pattern = re.compile(ref["name"]["pattern"])
    out = []
    for i, item in enumerate(items):
        at = f"{at_prefix}[{i}]"
        if isinstance(item, str):
            if not str_pattern.match(item):
                out.append(_finding("schema", f"{at} does not match the {defs_key} pattern: {item!r}", at))
        elif isinstance(item, dict):
            name = item.get("name")
            if not isinstance(name, str) or not name_pattern.match(name):
                out.append(_finding("schema", f"{at} is a table without a valid name", f"{at}.name"))
            if per_table:
                out += per_table(item, at, ref)
    return out

def _check_mcp_list(items, schema):
    if not isinstance(items, list):
        return []
    server = _schema_get(schema, "$defs", "mcpServer", "properties")
    transports, trusts = set(server["transport"]["enum"]), set(server["trust"]["enum"])
    out = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        at = f"primitives.mcp[{i}]"
        if not item.get("name"):
            out.append(_finding("schema", f"{at} is missing name", f"{at}.name"))
        transport = item.get("transport")
        if not transport:
            out.append(_finding("schema", f"{at} is missing transport", f"{at}.transport"))
        elif transport not in transports:
            out.append(_finding("schema", f"{at}.transport is not one of {sorted(transports)}: {transport!r}", f"{at}.transport"))
        trust = item.get("trust")
        if trust is not None and trust not in trusts:
            out.append(_finding("schema", f"{at}.trust is not one of {sorted(trusts)}: {trust!r}", f"{at}.trust"))
    return out

def _check_permissions(perms, schema):
    if not isinstance(perms, dict):
        return []
    unattended = perms.get("unattended")
    enum = set(_schema_get(
        schema, "properties", "primitives", "properties", "permissions",
        "properties", "unattended", "enum",
    ))
    if unattended is not None and unattended not in enum:
        return [_finding(
            "schema", f"primitives.permissions.unattended is not one of {sorted(enum)}: {unattended!r}",
            "primitives.permissions.unattended",
        )]
    return []

def _check_loops_schema(loops, schema):
    if not isinstance(loops, list):
        return []
    goal_recipe = _schema_get(schema, "$defs", "goalRecipe")
    name_pattern = re.compile(goal_recipe["properties"]["name"]["pattern"])
    out = []
    for i, loop in enumerate(loops):
        if not isinstance(loop, dict):
            continue
        at = f"primitives.loops[{i}]"
        for key in goal_recipe["required"]:
            if key != "stops" and key not in loop:  # rule 2 ("stops") owns that field
                out.append(_finding("schema", f"{at} is missing required key: {key}", f"{at}.{key}"))
        name = loop.get("name")
        if name is not None and not name_pattern.match(str(name)):
            out.append(_finding("schema", f"{at}.name does not match the goal recipe name pattern: {name!r}", f"{at}.name"))
    return out

def _check_schema(manifest, schema):
    out = []
    if manifest.get("version") != 1:
        out.append(_finding("schema", "version is missing or is not 1", "version"))
    for key in schema["required"]:
        if key not in manifest:
            out.append(_finding("schema", f"missing required key: {key}", key))
    known_top = set(schema["properties"])
    for key in manifest:
        if key not in known_top:
            out.append(_finding("schema", f"unknown top-level key: {key}", key))

    project = manifest.get("project")
    if isinstance(project, dict):
        name = project.get("name")
        if not isinstance(name, str) or not name.strip():
            out.append(_finding("schema", "project.name is missing or empty", "project.name"))
        commands = project.get("commands")
        test_cmd = commands.get("test") if isinstance(commands, dict) else None
        if not isinstance(test_cmd, str) or not test_cmd.strip():
            out.append(_finding("schema", "project.commands.test is missing or empty", "project.commands.test"))
        rb = project.get("review_bandwidth")
        if rb is not None and (isinstance(rb, bool) or not isinstance(rb, int) or rb < 1):
            out.append(_finding("schema", "project.review_bandwidth must be an integer >= 1", "project.review_bandwidth"))

    harness_enum = set(_schema_get(schema, "properties", "harnesses", "items", "enum"))
    harnesses = manifest.get("harnesses")
    if isinstance(harnesses, list):
        if not harnesses:
            out.append(_finding("schema", "harnesses must not be empty", "harnesses"))
        out += [
            _finding("schema", f"unknown harness id: {h!r}", f"harnesses[{i}]")
            for i, h in enumerate(harnesses) if h not in harness_enum
        ]

    pathway = manifest.get("pathway")
    if isinstance(pathway, dict) and not pathway.get("profile"):
        out.append(_finding("schema", "pathway.profile is missing", "pathway.profile"))

    registries = manifest.get("registries")
    if isinstance(registries, list):
        pattern = re.compile(_schema_get(schema, "properties", "registries", "items", "pattern"))
        out += [
            _finding("schema", f"registries[{i}] does not match the registry pattern: {r!r}", f"registries[{i}]")
            for i, r in enumerate(registries) if not isinstance(r, str) or not pattern.match(r)
        ]

    primitives = manifest.get("primitives")
    if isinstance(primitives, dict):
        known_primitives = set(_schema_get(schema, "properties", "primitives", "properties"))
        out += [
            _finding("schema", f"unknown key under primitives: {k}", f"primitives.{k}")
            for k in primitives if k not in known_primitives
        ]
        out += _check_instructions(primitives.get("instructions"), schema)
        for key in ("skills", "commands", "hooks"):
            out += _check_ref_list(primitives.get(key), f"primitives.{key}", schema, "primitiveRef")
        out += _check_ref_list(primitives.get("agents"), "primitives.agents", schema, "agentRef", _agent_enum_findings)
        out += _check_mcp_list(primitives.get("mcp"), schema)
        out += _check_permissions(primitives.get("permissions"), schema)
        out += _check_loops_schema(primitives.get("loops"), schema)

    state = manifest.get("state")
    if isinstance(state, dict):
        d = state.get("dir")
        if d is not None and not isinstance(d, str):
            out.append(_finding("schema", "state.dir must be a string", "state.dir"))

    return out

_STOPS_MESSAGE = (
    "all three hard stops are required (max_iterations, no_progress_after, budget_usd) "
    "— never default a missing stop"
)

def _check_stops(manifest):
    primitives = manifest.get("primitives")
    loops = primitives.get("loops") if isinstance(primitives, dict) else None
    if not isinstance(loops, list):
        return []
    out = []
    for i, loop in enumerate(loops):
        if not isinstance(loop, dict):
            continue
        at = f"primitives.loops[{i}].stops"
        stops = loop.get("stops")
        if not isinstance(stops, dict):
            out.append(_finding("stops", _STOPS_MESSAGE, at))
            continue
        for field in ("max_iterations", "no_progress_after", "budget_usd"):
            if field not in stops:
                out.append(_finding("stops", _STOPS_MESSAGE, f"{at}.{field}"))
        for field in ("max_iterations", "no_progress_after"):
            if field in stops and not _is_positive_int(stops[field]):
                out.append(_finding("stops", f"{field} must be an integer >= 1", f"{at}.{field}"))
        if "budget_usd" in stops:
            v = stops["budget_usd"]
            if not (isinstance(v, (int, float)) and not isinstance(v, bool)) or v <= 0:
                out.append(_finding("stops", "budget_usd must be a number > 0", f"{at}.budget_usd"))
    return out

def _check_verify_loop(manifest):
    out = []
    project = manifest.get("project")
    if isinstance(project, dict):
        commands = project.get("commands")
        if isinstance(commands, dict) and commands.get("test") == TEST_PLACEHOLDER:
            out.append(_finding(
                "verify-loop",
                f"project.commands.test is still the placeholder ({TEST_PLACEHOLDER!r}) "
                "— the agent cannot prove its work",
                "project.commands.test",
            ))
    primitives = manifest.get("primitives")
    loops = primitives.get("loops") if isinstance(primitives, dict) else None
    if isinstance(loops, list):
        for i, loop in enumerate(loops):
            if isinstance(loop, dict) and isinstance(loop.get("verify"), str) and not loop["verify"].strip():
                out.append(_finding("verify-loop", "loop verify command is empty", f"primitives.loops[{i}].verify"))
    return out

def _check_judge_family(manifest):
    project = manifest.get("project")
    models = project.get("models") if isinstance(project, dict) else None
    if not isinstance(models, dict):
        return []
    primary, judge = models.get("primary"), models.get("judge")
    if not isinstance(primary, dict) or not isinstance(judge, dict):
        return []
    primary_family, judge_family = primary.get("family"), judge.get("family")
    if primary_family and judge_family and primary_family == judge_family:
        return [_finding(
            "judge-family",
            "project.models.judge.family must differ from project.models.primary.family "
            "(case-sensitive) — the maker must not grade its own work",
            "project.models.judge.family",
        )]
    return []

def _check_env_value(manifest):
    primitives = manifest.get("primitives")
    mcp = primitives.get("mcp") if isinstance(primitives, dict) else None
    if not isinstance(mcp, list):
        return []
    out = []
    for i, server in enumerate(mcp):
        env = server.get("env") if isinstance(server, dict) else None
        if not isinstance(env, list):
            continue
        for j, entry in enumerate(env):
            if not isinstance(entry, str) or not ENV_NAME_RE.match(entry):
                out.append(_finding(
                    "env-value", f"primitives.mcp[{i}].env[{j}] must be a bare env var NAME, not a value: {entry!r}",
                    f"primitives.mcp[{i}].env[{j}]",
                ))
    return out

def _is_safe_name(name):
    """Mirrors aesop src/safety.ts isSafeName's separator/traversal checks. Deliberately does
    NOT flag an empty string: rule "schema" already owns missing/empty names (each fixture
    must trip exactly one rule), so emptiness is out of scope here — only "." and the
    separator/traversal/NUL cases are."""
    return (
        isinstance(name, str) and name != "."
        and ".." not in name and "/" not in name and "\\" not in name and "\x00" not in name
    )

def _check_unsafe_names(manifest):
    out = []
    project = manifest.get("project")
    if isinstance(project, dict):
        name = project.get("name")
        if isinstance(name, str) and not _is_safe_name(name):
            out.append(_finding("unsafe-name", f"project.name is not a safe name: {name!r}", "project.name"))

    primitives = manifest.get("primitives")
    if not isinstance(primitives, dict):
        return out

    # mcp/loops entries are always tables, never bare strings, so `_ref_name` naturally
    # resolves their name via `.get("name")` and the `.name` suffix below always applies.
    for key in ("skills", "commands", "hooks", "agents", "mcp", "loops"):
        for i, item in enumerate(primitives.get(key) or []):
            name = _ref_name(item)
            if isinstance(name, str) and not _is_safe_name(name):
                at = f"primitives.{key}[{i}]" if isinstance(item, str) else f"primitives.{key}[{i}].name"
                out.append(_finding("unsafe-name", f"primitives.{key}[{i}] is not a safe name: {name!r}", at))

    return out

def _check_secrets(raw_text):
    out = []
    lines = raw_text.split("\n")
    for pattern, what in SECRET_PATTERNS:
        for i, line in enumerate(lines):
            if pattern.search(line):
                out.append(_finding("secret", f"{what} committed in config — move it to an env var", f"line {i + 1}"))
                break
    return out

def validate(manifest, raw_text, schema):
    """Return a deterministic, ordered list of Finding dicts (code, message, at). Pure — no
    I/O, no clock. Checks run in this fixed order: schema, stops, verify-loop, judge-family,
    env-value, unsafe-name, secret."""
    out = []
    out += _check_schema(manifest, schema)
    out += _check_stops(manifest)
    out += _check_verify_loop(manifest)
    out += _check_judge_family(manifest)
    out += _check_env_value(manifest)
    out += _check_unsafe_names(manifest)
    out += _check_secrets(raw_text)
    return out

# Primitive id -> the primitives.<key> list/table whose non-emptiness means "declared".
# instructions/state are always declared (aesop always emits AGENTS.md + tasks/ convention).
_PLAN_DECLARED_KEYS = {
    "skill": "skills", "agent": "agents", "command": "commands", "hook": "hooks",
    "mcp": "mcp", "loop": "loops", "permissions": "permissions",
}

def _is_declared(primitive_id, primitives):
    if primitive_id in ("instructions", "state"):
        return True
    return bool(primitives.get(_PLAN_DECLARED_KEYS[primitive_id]))

def plan(manifest, matrix, harnesses=None):
    """Pure: what each harness in `harnesses` (or, if None, manifest["harnesses"]) would get
    for this manifest — native vs fallback, per primitives/harness-matrix.json (PLAN D7).
    Works for a harness the manifest does not declare (e.g. Cursor on a Copilot-only
    manifest); the caller is responsible for validating the manifest and any --harness id
    against the matrix first, and for wrapping the result with {"manifest": path} for
    --json. Returns {"harnesses": {"<id>": {"goal_mode", "primitives": [9 entries]}}}."""
    harness_ids = harnesses if harnesses is not None else (manifest.get("harnesses") or [])
    primitives = manifest.get("primitives") or {}
    out_harnesses = {}
    for h in harness_ids:
        spec = matrix["harnesses"][h]
        rows = []
        for pid in matrix["primitives"]:
            cell = spec["cells"][pid]
            rows.append({
                "id": pid,
                "declared": _is_declared(pid, primitives),
                "support": cell["support"],
                "target": cell["target"],
                "notes": cell["notes"],
            })
        out_harnesses[h] = {"goal_mode": spec["goal_mode"], "primitives": rows}
    return {"harnesses": out_harnesses}

def render_matrix_markdown(matrix):
    """Pure: the exact markdown table docs/PRIMITIVES.md embeds between its markers (PLAN
    D8) — nine primitive rows in model order, one column per harness in the matrix's own
    order, cell text is the support value only. T8 imports and calls this directly (never
    the CLI) so its drift test compares generator output, not a CLI byte-capture. LF-only,
    no trailing newline (the CLI's `print` supplies the one trailing newline)."""
    harness_ids = list(matrix["harnesses"])
    lines = ["| Primitive | " + " | ".join(harness_ids) + " |"]
    lines.append("| " + " | ".join(["---"] * (len(harness_ids) + 1)) + " |")
    for pid in matrix["primitives"]:
        supports = [matrix["harnesses"][h]["cells"][pid]["support"] for h in harness_ids]
        lines.append(f"| {pid} | " + " | ".join(supports) + " |")
    goal_modes = " · ".join(f"{h}={matrix['harnesses'][h]['goal_mode']}" for h in harness_ids)
    lines.append("")
    lines.append(f"Goal modes: {goal_modes}")
    return "\n".join(lines)

# -------------------------------------------------------------------------- CLI ---

def cmd_model(args):
    model = load_model()
    if args.json:
        print(json.dumps(model, indent=2, sort_keys=True))
        return 0
    for p in model["primitives"]:
        print(f"{p['id']}  {p['title']}  {p['manifest_key']}  {p['semantics']}")
    return 0

def cmd_matrix(args):
    if args.markdown:
        if args.harness is not None:
            print("error: --markdown cannot be combined with --harness", file=sys.stderr)
            return 1
        print(render_matrix_markdown(load_matrix()))
        return 0

    matrix = load_matrix()
    schema = load_schema()
    harness_enum = _schema_get(schema, "properties", "harnesses", "items", "enum")
    if args.harness is not None and args.harness not in harness_enum:
        print(f"error: unknown harness: {args.harness!r} — must be one of: {', '.join(harness_enum)}", file=sys.stderr)
        return 2

    harnesses = [args.harness] if args.harness else sorted(matrix["harnesses"])
    if args.json:
        print(json.dumps({h: matrix["harnesses"][h] for h in harnesses}, indent=2, sort_keys=True))
        return 0

    for harness in harnesses:
        if len(harnesses) > 1:
            print(f"# {harness}")
        cells = matrix["harnesses"][harness]["cells"]
        for primitive in matrix["primitives"]:
            cell = cells[primitive]
            print(f"{primitive}  {cell['support']}  {', '.join(cell['target'])}")
    return 0

def _load_manifest_for_cli(path):
    """Shared read+parse path for `check` and `plan`, both of which need the raw text
    (secret scan / validate()) alongside the parsed dict. Returns (raw_text, manifest, None)
    on success, or (None, None, error_message) on a missing file or malformed TOML."""
    try:
        raw_text = _read_manifest_text(path)
    except ManifestError as e:
        return None, None, str(e)
    try:
        return raw_text, tomllib.loads(raw_text), None
    except tomllib.TOMLDecodeError as e:
        return None, None, str(e)

def _print_findings(findings):
    for f in findings:
        print(f"{f['code']}  {f['at']}  {f['message']}")
    print(f"{len(findings)} finding{'s' if len(findings) != 1 else ''}")

def cmd_check(args):
    path = args.manifest
    raw_text, manifest, error = _load_manifest_for_cli(path)
    if error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    findings = validate(manifest, raw_text, load_schema())

    if args.json:
        print(json.dumps({"manifest": path, "ok": not findings, "findings": findings}))
    elif not findings:
        print(f"ok: {path}")
    else:
        _print_findings(findings)

    return 2 if findings else 0

def cmd_plan(args):
    path = args.manifest
    raw_text, manifest, error = _load_manifest_for_cli(path)
    if error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    schema = load_schema()
    findings = validate(manifest, raw_text, schema)
    if findings:  # a plan over an invalid manifest is misleading — even one "secret" finding blocks
        if args.json:
            print(json.dumps({"manifest": path, "ok": False, "findings": findings}))
        else:
            _print_findings(findings)
        return 2

    harness_ids = None
    if args.harness is not None:
        harness_enum = _schema_get(schema, "properties", "harnesses", "items", "enum")
        if args.harness not in harness_enum:
            print(f"error: unknown harness: {args.harness!r} — must be one of: {', '.join(harness_enum)}", file=sys.stderr)
            return 2
        harness_ids = [args.harness]

    result = plan(manifest, load_matrix(), harness_ids)

    if args.json:
        print(json.dumps({"manifest": path, **result}))
        return 0

    for h, spec in result["harnesses"].items():
        print(f"## {h}  (goal mode: {spec['goal_mode']})")
        for p in spec["primitives"]:
            declared = "declared" if p["declared"] else "—"
            print(f"{p['id']:<12}  {declared:<9}  {p['support']}  {', '.join(p['target'])}")
    return 0

def build_parser():
    parser = argparse.ArgumentParser(prog="primitives.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_model = sub.add_parser("model", help="print the nine-primitive model")
    p_model.set_defaults(func=cmd_model)

    p_matrix = sub.add_parser("matrix", help="print the per-harness support matrix")
    p_matrix.add_argument("--harness", default=None, help="limit output to one harness id")
    p_matrix.add_argument("--markdown", action="store_true", help="print the docs/PRIMITIVES.md table (no --harness)")
    p_matrix.set_defaults(func=cmd_matrix)

    p_check = sub.add_parser("check", help="validate a TOML manifest against the vendored schema")
    p_check.add_argument("manifest", help="path to the TOML manifest")
    p_check.set_defaults(func=cmd_check)

    p_plan = sub.add_parser("plan", help="preview what each harness would get for a manifest")
    p_plan.add_argument("manifest", help="path to the TOML manifest")
    p_plan.add_argument("--harness", default=None, help="preview one harness, declared or not (PLAN D7)")
    p_plan.set_defaults(func=cmd_plan)

    for p in (p_model, p_matrix, p_check, p_plan):
        p.add_argument("--json", action="store_true", help="machine-readable output")

    return parser

def main(argv=None):
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # PLAN D6 reserves exit code 2 for validation findings; argparse's own usage-error
        # code (also 2) is remapped to 1 so the two meanings never collide on the CLI.
        return 0 if exc.code == 0 else 1
    return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())
