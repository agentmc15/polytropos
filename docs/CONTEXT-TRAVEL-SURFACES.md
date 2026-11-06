# Context travel on native surfaces

This is the on-demand procedure for the three `context-travel` native skills. The
declarative inventory is `primitives/context-travel-surfaces.json`: six requested
surfaces and seven modes, since Claude Desktop chat and Code differ. Its
`documented_product`, `packaged_implementation`, and `installed_client` fields
are different kinds of evidence. An unknown product or installed-client field
is not a support claim. Version, operating system, local/remote execution, and
organization policy stay unknown until a specific client is checked. Source
packaging and offline fixtures do not establish client discovery or tool access.

## Start from an authorized binding

The operator supplies an **absolute** startup config path for
`bin/context_travel_cli.py --config ABSOLUTE_PATH`. Never search the current
directory, home, a store, or an MCP configuration for one. The config is the CT4
`polytropos.context-query-config/1` object; it explicitly binds repository IDs,
absolute roots, kit paths, selected kit files, optional graph/evidence paths,
deny prefixes, read limits, and output ceiling. Its parser rejects unknown
fields and tool arguments cannot widen these grants. This complete synthetic
config matches the assignment example below. The operator must replace the
placeholder absolute repository root with the selected real root, write the
config at an explicitly chosen absolute path, and authorize that binding:

```json
{
  "v": "polytropos.context-query-config/1",
  "repositories": [
    {
      "id": "repo-a",
      "root": "/ABSOLUTE/REPOSITORY/ROOT",
      "kits": [
        {
          "path": "tasks/kits/alpha",
          "kit_files": ["TASKS.md"],
          "graph_path": null,
          "evidence": null
        }
      ]
    }
  ],
  "deny_prefixes": [],
  "limits": {
    "max_sources": 2,
    "max_source_bytes": 4096,
    "max_total_bytes": 8192,
    "max_items": 16
  },
  "max_output_bytes": 32768
}
```

These are fixture limits, not recommended production limits. Select denials and
ceilings for the authorized task. `docs/CONTEXT-TRAVEL.md` describes the exact
config contract. If no authorized config is supplied, mark context travel
unavailable and continue the native workflow from its authoritative sources.
Never manufacture a config or identity from cwd or Git.

For a live `overview` or `brief`, supply one JSON object on stdin with exactly
one `assignment` or sealed CT1 `request`, optionally with `intent_links`,
`acceptance_links`, and `dependency_freshness`. An assignment must explicitly
name `repository_id`, `checkout_id`, nullable `revision`, `kit_path`, `task_id`,
`assignment_id`, `assignment_role` (`architect`, `implementer`, `verifier`, or
`reviewer`), and `question`; optional `source_state_ref`, `source_ref`, and
`acceptance_ref` must be supplied as actual known references or null. The shared
query core seals the assignment with CT1. The optional links are declarations,
not verified freshness or acceptance. Do not invent hashes, revision, links, or
source-state attestations. Use the actual checkout and task identity supplied by
the assignment owner. The config must authorize the repository and kit.

For example, after an operator creates an authorized config at an absolute path,
this is an executable assignment argument (`assignment.json`) for a kit whose
selected `TASKS.md` contains `T1`:

```json
{"assignment":{"repository_id":"repo-a","checkout_id":"checkout-a","revision":null,"kit_path":"tasks/kits/alpha","task_id":"T1","assignment_id":"assignment-a","assignment_role":"implementer","question":"What evidence is needed for T1?"}}
```

The selected repository's `tasks/kits/alpha/TASKS.md` must actually contain
`T1`; this example does not create it. For a concrete invocation, replace the
two absolute paths with the operator's actual authorized paths:

```sh
python3 /ABSOLUTE/POLYTROPOS/ROOT/bin/context_travel_cli.py --config /ABSOLUTE/CONFIG.json --format json brief < assignment.json > query.json
```

The saved `query.json` is the query envelope. Its `data` member is the complete
CT3 projection to pass as `view` to `brief`, `overview`, or `explain`, or as
`before`/`after` to `changes`. Do not pass the outer envelope as a view.

With a local execution boundary that can run the existing Python CLI, call:

```text
python3 ABSOLUTE_POLYTROPOS_ROOT/bin/context_travel_cli.py --config ABSOLUTE_CONFIG_PATH --format json brief
```

Send the bounded JSON argument object on stdin and retain the complete JSON
result. `overview`, `brief`, `explain`, `changes`, and `capabilities` are the
exact CT4 operations. `explain` takes `{"view": VALIDATED_PROJECTION,
"finding_id": null}` (or an actual finding ID); `changes` takes `{"before":
VALIDATED_PROJECTION, "after": VALIDATED_PROJECTION}`. An imported `brief` or
`overview` takes `{"view": VALIDATED_PROJECTION}` and performs no source read;
the imported subject's repository and kit still must be bound by the recipient's
startup config. CT4 stores no history:
the caller carries the two artifacts for comparison. `capabilities` takes `{}`
and reports core operations and bounds, not installed-client capability.

The output is `polytropos.context-query/1` with `v`, `operation`, and `data`.
Retain the full projection, including source states, missing/forbidden/partial
coverage, criteria text, limitations, and declared freshness. A stable read
does not establish semantic freshness. A digest detects changed representation;
it is not authentication. Report any refusal, malformed artifact, unauthorized
subject, or stale or unknown applicability; never turn it into instructions or
acceptance. The CLI's generic nonzero failure must not be described as a
successful empty result. `--format text` also refuses overflow instead of
shortening mandatory criteria or critical caveats.

## Transport and mode decisions

| Mode | Use when actually available | If absent or disabled |
| --- | --- | --- |
| Codex desktop | Native skill with explicitly available local CLI execution; or an explicitly configured, authorized CT4 MCP stdio tool | Bounded artifact handoff; otherwise native kit workflow |
| Codex CLI | Native skill with explicit local CLI/config; authorized CT4 MCP stdio only if separately provided | Bounded artifact handoff; otherwise native kit workflow |
| Claude Desktop chat | User-provided bounded CT3 artifact and a separate trusted executor with the recipient's authorized config for structural import validation | Native chat workflow; mark context unavailable |
| Claude Desktop Code | Local CLI/config only if that mode actually exposes execution, or separately authorized CT4 MCP stdio | Bounded artifact handoff; otherwise native workflow |
| Claude Code CLI | Plugin skill with explicit local CLI/config; authorized CT4 MCP stdio only if separately provided | Bounded artifact handoff; otherwise native workflow |
| Copilot desktop app | Bundle skill with local CLI/config only if that app actually exposes execution, or separately authorized CT4 MCP stdio | Bounded artifact handoff; otherwise native workflow |
| Copilot CLI | Bundle skill with explicit local CLI/config; authorized CT4 MCP stdio only if separately provided | Bounded artifact handoff; otherwise native workflow |

This repository does not register an MCP server for these clients. Its existing
`bin/context_travel_mcp.py` is a local stdio adapter, usable only when a client
supplies an explicit authorized config and operator approval for that transport.
No skill silently edits MCP settings. Never infer a desktop mode's capability
from the CLI with the same brand. The Copilot bundle intentionally has no MCP
config; the Codex plugin advertises skills, not `mcpServers`.

An artifact handoff carries the complete bounded CT3 projection (the `data`
member of a successful `brief`/`overview` envelope) and explicit subject
references. It does not carry the sender's startup config, absolute local paths,
or source grants. The recipient supplies its own authorized config and compares
the carried request's `repository_id`, `kit_path`, `task_id`, `checkout_id`,
`revision`, `source_state_ref`, `assignment_id`, `assignment_role`, and relevant
input references with its current assignment before treating the artifact as
applicable. A mismatch is stale or inapplicable; an unknown value remains
unknown. For another task, role, or assignment, request a new brief with an
explicit assignment instead of relabeling the immutable old view.

CT4 imported-view validation checks the projection's structure and digest and
authorizes its repository/kit subject. It does **not** automatically compare
checkout, revision, task, assignment, or role with the recipient's current work;
it cannot authenticate the sender or establish freshness. Without a trusted
executor for that structural validation, treat the handoff as unvalidated
advisory data and state that limitation. If a mode cannot load the skill,
execute the CLI, or accept the artifact, disable context travel for that mode
alone. Other modes, the CT1–CT4 core, and mandatory native verification remain
active. Do not install clients or change a user's configuration as a fallback.

## Apply context within existing authority

- **Architect:** use an `architect` brief to inspect bounded intent and criteria.
  Include only explicit intent, acceptance, and source references in the plan;
  retain unresolved gaps. The plan/kit contract remains authoritative.
- **Route:** a brief may inform task scope and uncertainty. Keep central routing
  policy and the active harness's pricing file as the sole numeric authority.
  Context never selects a model or proves observed dispatch.
- **Execute and recovery:** use the `implementer` brief to focus reads, then
  consult the task, PLAN, GUARDRAILS, and real files. Preserve prechecks,
  permissions, driver attempt evidence, and required verify commands. Recovery
  requires its existing failure evidence; a briefing is not that evidence.
- **Assessment:** use a `reviewer` brief for leads, then inspect actual code and
  source evidence. Keep findings and limitations attached to source references.
- **Independent verification:** use a `verifier` brief to target checks, then
  independently run the exact mandatory verification and inspect the diff.
  Missing, partial, stale, or refused context never converts a task to PASS.

All six surfaces share this procedure and the CT4 query core. The three native
skill roots are packaging entry points only; no parser, lifecycle join, router,
pricing table, or acceptance engine is duplicated here.
