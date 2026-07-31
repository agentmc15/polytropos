# Privacy — what stays local, what is committed, and the before-going-public checklist

**This repository is the public snapshot.** It was born via option (b) of the checklist below: a single root commit from a scrubbed snapshot of a private original — commit history and its author metadata left behind, ledger dollar figures and `session:` transcript ids redacted, absolute home paths generalized to `/path/to/polytropos`. The private original retains full history.

The design below is inherited from that original, where the working stores live. Its privacy model has two tiers, and the distinction matters
the day anyone considers flipping it public.

## Never committed (enforced, not habitual)

These live only on this machine. Each is guarded by a root-anchored `.gitignore` rule
AND by `tests/test_privacy_layout.py`, which fails the whole suite — and therefore every
kit task's verify command — if any of them ever becomes tracked:

| Surface | Contents |
|---|---|
| `journal/` | daily digests, summaries, inbox, plan cards, `config.json` (repo paths) |
| `telemetry/` | dated cost/usage/routing envelopes (real dollar figures) |
| `memory/` | user memory facts |
| `prefs/` | model pins/excludes |
| `trends/` | routing-history snapshots |
| `value-report*.html` | generated value reports (dollars, session ids, machine paths) |

Zero files under any of these have ever been committed, verified across the full git
history (`git log --all --diff-filter=A`) on 2026-07-25.

## Committed by design (private-repo tier)

The following personal *metadata* IS in the tracked tree and git history, deliberately —
it is the raw material of the routing scorecard and the kit ledgers:

- **Aggregate dollar figures** in `.claude/kits/*/NOTES.md` ledgers, a few commit
  messages, and merged PR bodies (e.g. actual-vs-counterfactual verdicts).
- **Session ids** (`session:` lines in kit ledgers) — needed for per-kit dollar
  attribution.
- **Absolute home paths** (`/Users/<name>/...`) throughout kit briefs and NOTES — kit
  briefs pin absolute paths by design.

No transcript text, message content, or credentials are committed anywhere.

## Before flipping this repo public — the checklist

The committed-by-design tier is acceptable in a private repo and is an exposure in a
public one. Before changing visibility, decide explicitly:

1. **Dollar figures + session ids + home paths in history**: either (a) accept them as
   public, (b) start a fresh public repo from a scrubbed snapshot (squash to one
   root commit with ledger dollar lines and `session:` lines redacted and home paths
   generalized), or (c) keep this repo private and publish a sanitized mirror.
   History rewriting after the fact does not un-publish anything already cloned —
   decide BEFORE the flip, not after.
2. **Merged PR bodies and commit messages** quoting dollar verdicts survive even a
   force-pushed history rewrite (GitHub retains PRs) — a fresh repo (b/c) is the only
   clean path if those must not be public.
3. Re-run `python3 -m unittest tests.test_privacy_layout` and confirm green.
4. Re-run `python3 bin/plugin_staleness.py` — an install refresh after any scrub keeps
   the local plugin coherent.

That decision was made for this repository: it is the option-(b) snapshot described at the top of this file. The checklist stays here for the next repo that faces the same flip.

## The iCloud lesson (2026-07-25)

Git guards are not the only remote channel. This repo originally lived under
`~/Desktop/reposV2` — and macOS Desktop & Documents sync meant the ENTIRE tree,
gitignored stores included, synced continuously to iCloud. The gitignore fortress guarded
the GitHub door while the whole house sat in Apple's cloud. Discovered by inode
comparison: `~/Desktop` and `~/Library/Mobile Documents/com~apple~CloudDocs/Desktop`
were the same directory.

Resolution: the repo moved to `~/Developer/reposV2` (outside iCloud's sync scope,
matching the same layout on the other machine), atomically (same volume, same inode —
nothing copied). Standing rules this creates:

- **This repo must live outside any cloud-synced folder** — never under `~/Desktop`,
  `~/Documents`, or any Dropbox/Drive/OneDrive tree. Verify with an inode or
  `CloudDocs` check, not by assumption.
- **iCloud retains deleted files ~30 days** ("Recently Deleted" in Files/Finder).
  Moving out stopped the ongoing sync; purging the historical copies requires a manual
  "Delete Immediately" in iCloud's Recently Deleted — server-side state no local
  command reaches.
- Historical kit briefs and NOTES pin the old `/Desktop/` absolute paths. They are
  records, not runtime config — but re-running an OLD kit's verify command verbatim
  will hit dead paths; translate to `/Developer/` when resurrecting one.
- The repo-location rule is now enforced, not habitual: `tests/test_privacy_layout.py`
  fails the whole suite if this checkout's path contains a cloud-synced component.

## The plugin-cache lesson (2026-07-25)

Plugin packaging is a third copy channel, and it ignores `.gitignore` too. `claude plugin
install` copies the **entire** plugin directory into
`~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/` — verified 2026-07-25: cache
versions 0.2.0 through 0.4.0 each hold full copies of `journal/` and `prefs/`, and 0.4.0
also holds `telemetry/` and `value-report.html`. Old version directories are not pruned
on update (0.1.0 through 0.4.0 all present; `claude plugin prune` removes orphaned
dependencies only). No exclusion mechanism exists as of 2026-07-25 — the plugin docs
offer no `.claudeignore` or include/exclude manifest field; the copy is total. The cache lives under `~/.claude` (local,
not cloud-synced), so the exposure is duplication and staleness rather than remote sync —
but every copy is one more place personal data sits, and one more thing to scrub before
any machine migration or support bundle.

There is also a latent **runtime** hazard: every store-writing script in `bin/` defaults
its store directory to the plugin root derived from its own file location
(`PLUGIN_ROOT / "journal"`, `/ "memory"`, `/ "telemetry"`, …). Run from the repo checkout
that is correct; run via `${CLAUDE_PLUGIN_ROOT}` from the *installed* plugin, the plugin
root **is the cache**, so a skill-dispatched run without an explicit `--*-dir` writes
personal data into a versioned cache directory that the next bump strands. As of
2026-07-25 every store file observed in the cache was an install-time copy (timestamps
match `installedAt`), so this has not fired yet — but it is one skill dispatch away.

Standing rules this creates:

- **After every version bump / plugin refresh**: delete the personal store directories
  (`journal/`, `prefs/`, `telemetry/`, `memory/`, `trends/`, `value-report*.html`) from
  the fresh cache copy, and remove stale version directories. Manual by design — repo
  code never touches `~/.claude`.
- **Never sync, back up, or share `~/.claude`** without the same scrub; the cache holds
  whatever the stores held at install time.
- **Open design item**: skill-dispatched store writes should anchor to the dev checkout,
  never the plugin root, so an installed-plugin run cannot write into the cache.

### The bump-and-prune runbook (validated 2026-07-26 on the 0.4.0 → 0.5.0 bump)

The prune belongs **immediately after** the reinstall, never before — the reinstall is what
recreates the exposure. Run these in order:

```bash
# 1. bump the version (the ONLY place it lives) and commit it
#    .claude-plugin/plugin.json  ->  "version": "<new>"

# 2. reinstall. `install` is a no-op when already installed at user scope —
#    `update` is what actually re-copies the tree.
claude plugin update polytropos@polytropos-local

# 3. LOOK at what the copy pulled in, before deleting (this is the exposure)
C=~/.claude/plugins/cache/polytropos-local/polytropos
for d in journal telemetry memory prefs trends; do
  test -e "$C/<new>/$d" && echo "!! $d ($(find "$C/<new>/$d" -type f | wc -l) files)"
done

# 4. prune the fresh copy AND the superseded version directory
rm -rf "$C/<new>"/{journal,telemetry,memory,prefs,trends} "$C/<new>"/value-report*.html
rm -rf "$C/<old>"

# 5. verify BOTH properties — clean, and actually current
find "$C" \( -path '*/journal/*' -o -path '*/telemetry/*' -o -path '*/prefs/*' \) -type f
ls "$C"                                    # only the new version should remain
```

Notes earned on the 0.5.0 run:

- **`install` does not refresh an existing install** — it reports "already installed" and
  changes nothing. Use `update`, or the bump silently never lands.
- **Step 5's `find` produces false positives**: `skills/journal/SKILL.md` and its Codex and
  Copilot twins match a `*/journal/*` glob and are legitimate tracked plugin files. Confirm any
  hit with `git ls-files --error-unmatch <path>` before treating it as personal data — the same
  root-anchoring distinction the repo's own `/journal/` gitignore rule exists to make.
- **Verify currency, not just cleanliness.** A stale install is the failure this runbook exists
  to prevent, and it is silent: before the 0.5.0 bump the cache had been pinned at 0.4.0 for a
  day, missing two shipped skills, a driver flag, and two pricing-roster models, while looking
  perfectly healthy. Check a file you know landed recently, not just that the stores are gone.
- **Restart Claude Code afterwards** — the updater says so, and new skills do not appear in the
  session that performed the update.
