# What "read-only target, mutation only under the run" actually covers — and its two carve-outs

Detail moved out of `skills/repo-bench/SKILL.md` by roadmap step 22 so the entry point carries the spend law and the relay requirements; the text below is unchanged.

The target repo is read-only by construction: every touch to it goes through one allowlisted,
read-only git choke point, and candidate work happens in tree-extraction sandboxes with no
history the candidate could mine for the answer. That guarantee is real, but it applies to
`run`'s candidate sandboxes specifically — it has two carve-outs worth knowing before you tell
a user "nothing is written outside the run":

- **`plan` has no run directory at all.** Mining for `plan` happens through a system temp
  directory, not under any run's own working area, because a plan-only invocation never creates
  a run in the first place. That temp directory is still local and disposable, but it is not
  "under the run dir" — there is no run dir yet.
- **The judge's dispatch runs from a system temp directory on purpose.** This is a leak fix,
  not an oversight, and the reason is stronger than "stray clues": the run directory holds
  `tasks/<id>.json`, which carries the reference patch and the withheld test blobs — literally
  the answer to "which of these two slots is the reference." A judge whose cwd sat inside the
  run tree could read it out of its own ancestry and the blind `Patch A`/`Patch B` design
  would be decoration. Two things enforce it: the judge's cwd is outside the run dir entirely,
  and the run's task/dispatch records are not written to disk at all until every dispatch,
  candidate and judge alike, has already returned.
