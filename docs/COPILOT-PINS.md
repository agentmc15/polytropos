# Copilot model prefs — pinning and excluding models

User model preferences for the Copilot CLI side of the optimizer: pin which model a tier
resolves to, and/or exclude models from consideration entirely. Copilot CLI only — no
Claude-side or Codex-side counterpart yet (see Deferred).

## 1. What it is / why

The roster in `data/pricing.copilot.json` maps each model id to a tier
(`cheap | mid | strong | frontier`). Sometimes the roster's tier-holder for a slot isn't the
model you want (a vendor swaps their frontier offering, or you'd rather never see a
particular id recommended) — and there's no way to say so short of hand-editing the pricing
file, the numeric source of truth, not a place for personal taste. Prefs fix that without
touching pricing data:

- **A pin** (`TIER=MODEL_ID`) says "when the driver or a skill resolves `TIER`, use
  `MODEL_ID`" — everywhere that tier is resolved, in initial dispatch and in the escalation
  ladder alike.
- **An exclude** (`MODEL_ID`) says "never use this model" — skipped in tier resolution and
  in the ladder, full stop.

**This is explicitly NOT a force-frontier switch.** A pin changes WHICH model a tier means;
it never changes WHEN a tier is used. The escalation trigger (verify failure) and the tier
walk-order (`cheap → mid → strong → frontier`) are untouched — prefs only decide what each
rung dispatches to once the driver has already decided to climb.

## 2. The prefs file

`prefs/copilot.json` at the repo root. It is gitignored user data (a root-anchored
`/prefs/` entry in `.gitignore`) — hand-edited, never committed, and never auto-created by
any engine. No sample file ships; you create it yourself if you want one.

Schema:

```json
{
  "schema_version": 1,
  "pins": {
    "frontier": "<frontier-model-id>",
    "mid": "<model-id>"
  },
  "excludes": ["<model-id>"]
}
```

`schema_version` is currently `1` (a newer value than the engine understands is read
best-effort with a note, never a crash); `pins` is a dict of tier name to model id, where
only `cheap`, `mid`, `strong`, `frontier` are valid tier keys; `excludes` is a list of model
ids never to use.

Every id above is a PLACEHOLDER — `<model-id>`, `<frontier-model-id>`. This doc never prints
a real pricing-key id (the roster changes; a stale example would rot). List the live ids
yourself before writing the file:

```bash
python3 bin/copilot_pricing.py models --json
```

A malformed file (bad JSON, `pins` not a dict of strings, `excludes` not a list of strings)
degrades to empty prefs plus a note — never a crash. A single stale entry (a tier not in the
vocabulary, or a model id that's fallen out of the roster) is skipped with a note naming it;
the rest of the file still applies.

## 3. Per-run flags + precedence

Both `bin/copilot_execute.py run` and `bin/copilot_pricing.py prefs` accept the same four
flags:

- `--pin TIER=MODEL_ID` — repeatable; resolve `TIER` to `MODEL_ID` for this run.
- `--exclude MODEL_ID` — repeatable; never dispatch/recommend this model for this run.
- `--prefs FILE` — read prefs from `FILE` instead of the default `prefs/copilot.json`.
- `--no-prefs` — ignore the prefs file entirely (`--pin`/`--exclude` flags still apply).

(`review` takes none of these — it dispatches the reviewer agent with no model resolution.)

Precedence:

- **Pins merge per-tier.** A flag pin replaces only its own tier's file pin; other file
  pins survive untouched — full replacement would make one `--pin` silently drop unrelated
  stored pins.
- **Excludes are the union** of file and flags, deduped — an exclude is a "never use this"
  statement, so accumulation is the only non-surprising reading.
- **`--no-prefs` ignores the file, keeps the flags** — the escape hatch for "use this model
  just this once" without editing or deleting your stored prefs.
- **A pin-vs-exclude conflict is always a hard error**, from any source combination (file
  pin vs. flag exclude, flag pin vs. file exclude, etc.), after the merge:

  ```
  pin <tier>=<id> conflicts with exclude <id> — drop one, or use --no-prefs to bypass the prefs file
  ```

  Both engines exit 2 on this — silently picking a winner is exactly the ambiguity prefs
  exist to remove.

## 4. Semantics

- **A pinned id wins its tier outright** — no file-order scan, the pin is the answer.
- **Cross-tier pins are deliberate overrides.** Pinning a `mid`-tier model into the
  `frontier` slot is legal; the engines note both tiers, and any cost estimate for that
  dispatch prices the pinned model at its own rates (no rate mixing — already how `est`
  works).
- **Excluded ids are skipped** in tier resolution and in the escalation ladder — the next
  model in pricing-file order for that tier is used instead.
- **An emptied tier is skipped**, same as the pre-existing empty-tier behavior with no
  prefs involved.
- **An emptied frontier with no replacing pin means the ladder tops out lower.** If
  excluding drains the frontier tier and no pin replaces it, the driver says the ladder tops
  out at the next tier down — it never fabricates a rung or invents an id.
- **A task's own TASKS.md model pin getting excluded** is handled at initial dispatch: the
  driver substitutes that tier's resolved model (the prefs pin if set, else the next live id
  in file order) and notes the substitution. If nothing resolves for that tier, it's a hard
  error telling you to un-exclude or pin — initial dispatch never silently jumps tiers
  (tier-jumping is the ladder's job, and fires only on verify failure).
- **Prefs do not reach an agent's own frontmatter `model:` default.** A task dispatched with
  no `--model` override still resolves through Copilot's own agent-frontmatter mechanism,
  which the driver never sees or influences — prefs affect only what the driver itself
  resolves and passes.

## 5. Seeing what's active

```bash
python3 bin/copilot_pricing.py prefs
```

With no prefs file and no flags, this prints the honest default: no pins, no excludes, each
tier resolving to the pricing file's file-order default. With prefs active, it prints the
source (the file path, `(no prefs file)`, or `(prefs file ignored: --no-prefs)`), the
active pins and excludes, every note (stale-entry skips, cross-tier annotations, schema
warnings), and a per-tier resolution table — pinned entries marked, an unresolvable tier
rendered honestly rather than invented. `--json` emits exactly `source`, `pins`, `excludes`,
`resolved` (tier to id or null), `resolved_via` (tier to `"pin"` / `"default"` / null), and
`notes`.

`bin/copilot_execute.py run --dry-run` shows the same idea from the dispatch side: with
active prefs it prints the effective (substituted) dispatch plus a `prefs:` line and any
notes; with no flags and no prefs file, its output is unchanged from before this feature
existed.

## 6. Where it's taught

Four Copilot skills — and their same-named agents — carry a short "User model prefs (pins &
excludes)" section: `route`, `frontier-check`, `architect`, `escalate` (skill and agent
surfaces for all four). Each teaches checking `copilot_pricing.py prefs` before recommending
anything, never recommending or pinning an excluded model, and treating a pinned tier's
model as that tier's pick outright; `frontier-check` additionally evaluates the pinned
frontier candidate, when one is set, instead of the roster's default pick. The `execute`
skill carries one sentence pointing at the driver's flags and the `prefs` command.

## 7. Deferred

Recorded, not built:

- **Codex-side and Claude-side prefs parity** — Copilot CLI only for now; a future kit would
  port the same pin/exclude idea to the other two harnesses.
- **A prefs-writing CLI** — no `prefs set` / interactive editor; the JSON file in section 2
  is hand-edited.
- **Prefs-aware `models` table markers** — the `models` subcommand doesn't flag pinned or
  excluded rows; the `prefs` subcommand is the one view for that today.
- **Reaching an agent's frontmatter `model:` default** — documented as a limitation in
  section 4, not a gap this feature closes; that resolution happens on Copilot's side, past
  where the driver can see it.
