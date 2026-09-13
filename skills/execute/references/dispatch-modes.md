# Dispatch modes — fresh fan-out vs warm sidekick

Detail moved out of `skills/execute/SKILL.md` by roadmap step 22 so the entry point carries the mandatory loop; the text below is the binding grammar it points at, unchanged.

Fresh, parallel subagents remain the default for tasks marked `independent:` with disjoint
files — one message, multiple Agent calls, no shared state (this rule is unchanged).

For a **cohesive cluster**, keep ONE warm implementer instead of paying N cold prompt-cache
starts: spawn it for the cluster's first task, then for each subsequent task continue the
SAME agent via SendMessage with the next brief — a continued agent keeps its context, and its
already-read files, intact, so the cluster's shared files are read and cached once. A
cohesive cluster is a maximal run of tasks that:

- form a serial `depends:` chain within one phase (each task depends on the previous), and
- share a primary file or subsystem — the same file named in their briefs, or the TASKS.md
  preamble flagging them as a same-file/serial chain (the architect leaves these hints), and
- carry the SAME `model` value. A continued agent keeps its spawn model and SendMessage
  cannot override it, so a model-pin change ALWAYS ends the cluster — the task's `model`
  field stays authoritative at dispatch; never serve an `opus`-pinned task with a warm
  `sonnet` agent, or vice versa.

The trade-off to respect: a warm agent accumulates context and eventually needs compaction,
which destroys the cache advantage — warmth is for clusters, not universal. Cap a warm
sidekick at ~4 tasks, end it early if its replies degrade or it reports context pressure, and
start the next cluster fresh. Each continuation message is still the next task's
self-contained brief verbatim, prefixed only with "Previous cluster task is done; next task:".
Verification is NEVER warmed: the verifier agent is always a fresh spawn — its value
IS the adversarial fresh context. Record warm-cluster use in NOTES.md (which tasks shared one
agent) so later phases and the scorecard can see it.
