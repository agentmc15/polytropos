The rosters are not a porting backlog with most of the boxes ticked. The routing *judgment*
is shared across all three harnesses; the mechanics deliberately are not, because each
harness bills differently, exposes different local data, and has a different idea of what a
"skill" even is. A dash in the matrix above is usually one of three things: a capability
that only makes sense where that harness's billing or plumbing makes it necessary, a
capability whose underlying data only one harness exposes, or the same job living under a
different name. Where a dash is simply "not built yet", it says so below.

### Claude Code only

- [cost-report](claude/cost-report.md) — reads Claude Code's own local transcripts. The
  other two harnesses answer the same question over their own logs, under
  [usage](copilot/usage.md).
- [fable-check](claude/fable-check.md) — the go/no-go for the specific frontier model in the
  Claude lineup. Copilot and Codex ask the identical question about *their* top tier and
  call it [frontier-check](copilot/frontier-check.md).
- [graphify](claude/graphify.md) — drives an external, user-installed graph CLI and feeds
  the resulting brief into planning. The reader engine behind it is harness-neutral and
  runs from any shell, so a Copilot or Codex session can use the same brief without a skill
  of its own.
- [repo-bench](claude/repo-bench.md) — benchmarks candidate *Claude* models on a repo's own
  real work, so the harness that dispatches the candidates is Claude Code by construction.
  A Codex adapter for the same engine is named as a future addition in the
  [Codex harness deep dive](../deep-dives/codex-harness.md).
- [setup](claude/setup.md) — installs the Claude Code statusline into Claude Code's own
  settings file. It configures exactly one harness; there is nothing to mirror.
- [update](claude/update.md) — the one surface where a dash means the opposite of missing:
  a single freshness card that reports on **all three** harness installs at once. It lives
  on Claude Code because it has to live somewhere.

### GitHub Copilot CLI only

- [budget](copilot/budget.md) — Copilot meters every model call against a finite AI-Credit
  balance that can run out mid-kit. A Claude subscription's cost is a rate-limit window
  that refills, and a Codex subscription run is usage-limited rather than credit-metered;
  neither has a balance to defend this way.
- [lessons-loop](copilot/lessons-loop.md) — vendored from the aesop registry with a
  Copilot-harness routing category added, rather than authored here for all three.
- [goliath](copilot/goliath.md) — an explicitly Copilot-CLI-only orchestration policy: five
  fixed roles whose model fallbacks resolve against the Copilot model picker. It does not
  configure or invoke another harness.

### OpenAI Codex CLI only

- [doctor](codex/doctor.md) — Codex is the only harness here whose install spreads across
  separately-owned pieces (a plugin, optional agents, and legacy copied surfaces tracked by
  an ownership manifest), so it is the only one with per-component install state worth
  diagnosing. The equivalent Claude and Copilot checks are folded into
  [update](claude/update.md).

### Present, under a different name

Some rows carry a dash because the capability is named for the harness it serves — and
one because it genuinely is not built yet:

- **effort** ([Copilot](copilot/effort.md), [Codex](codex/effort.md)) — on Claude Code the
  effort dial is a session setting you control directly, and the guidance for using it
  rides inside [route](claude/route.md) rather than in a skill of its own.
- **frontier-check** ([Copilot](copilot/frontier-check.md), [Codex](codex/frontier-check.md))
  — Claude Code's version is [fable-check](claude/fable-check.md), named for the model it
  asks about.
- **usage** ([Copilot](copilot/usage.md), [Codex](codex/usage.md)) — each reads its own
  harness's local session logs; Claude Code's is [cost-report](claude/cost-report.md).
- **memory** ([Claude Code](claude/memory.md), [Codex](codex/memory.md)) — this one is
  genuinely not built for Copilot yet, and the
  [memory deep dive](../deep-dives/memory-skill.md) records it as deferred rather than
  rejected: the store and its engines are harness-neutral, so a port is possible. In the
  meantime [lessons-loop](copilot/lessons-loop.md) covers the adjacent need on Copilot —
  durable corrections written down so they are not relearned.
