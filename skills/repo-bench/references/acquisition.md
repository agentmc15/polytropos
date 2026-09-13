# The two acquisition modes, and `--with-gh`

Detail moved out of `skills/repo-bench/SKILL.md` by roadmap step 22 so the entry point carries the spend law and the relay requirements; the text below is unchanged.

- **Issue-replay** engages when the target's `git log` yields enough fix commits that
  reference an issue (`fixes/closes/resolves #N`, or a squash-merge `(#N)` subject) to clear
  the evidence floor below. Each pair becomes a task: the commit before the fix is the base,
  the fix diff is the reference patch (never shown to the candidate), and the problem
  statement is the issue title/body when available, else the commit message — labelled
  `statement from commit message (weaker than issue text)` when it falls back.
- **General (mutation-repair)** is the fallback: a deterministic textual mutation (comparison
  flip, boolean negation, off-by-one, and/or swap) is applied to the repo and validated RED —
  the caller's `--test-cmd` must actually fail with the mutation in place, at zero model cost —
  before the task is admitted. The candidate is told the tests fail and must find and fix it;
  the reverse-mutation diff is the reference patch. This mode requires `--test-cmd`.

`--mode auto` (the default) prefers issue-replay and falls back honestly to general; the plan
card states which mode was chosen and why, including how many mined pairs actually carry a
usable tests oracle — an issue-replay pair can mine cleanly and still have no test coverage to
score it, so "enough pairs" and "enough *scorable* pairs" are not the same claim. `--mode` can
force either mode explicitly.

### `--with-gh` — real issue text instead of the commit message

Issue-replay's default statement is the fix commit's own subject+body, labelled
`statement from commit message (weaker than issue text)`. That label matters most on repos
that squash-merge PR descriptions into the merge commit: a PR description usually describes
the CURE, not the bug (it can even name a private helper the fix itself introduces), while the
issue body describes the actual bug the candidate needs to find. `--with-gh` (opt-in, accepted
by both `plan` and `run`) calls `gh api repos/<owner>/<name>/issues/<N>` once per
issue-referencing task and, when it succeeds AND the number is a genuine issue, uses the real
issue text — `statement_source` becomes `issue` and the weaker-statement label drops.

**GitHub shares ONE number namespace between issues and pull requests, and a squash-merge
`(#N)` subject is usually a PR number, not an issue number.** `gh issue view` cannot tell the
two apart — it resolves a PR number happily and returns the PR's own description, which is a
WORSE leak than the commit message: a PR description explains the fix in detail (it can name
symbols the fix introduces that the bug report never mentions), so blindly using it made
enrichment more confident and less trustworthy at the same time. `--with-gh` therefore never
calls `gh issue view`. It calls `gh api repos/<owner>/<name>/issues/<N>` — the same underlying
GitHub object as raw JSON — and inspects the payload for a `pull_request` key, which GitHub's
REST API sets if and only if the number is a pull request. **When that key is present, the PR
body (and its title) are never used**, full stop; mining falls back to the commit-message
statement with the existing weaker-statement label plus a note identifying the number as a
pull request. `statement_source: issue` therefore always means a genuine issue was used — it
is the field a reader relies on to weigh a verdict, so it must never overstate.

Requirements: `gh` installed and authenticated (`gh auth login`) locally — it is never invoked
by any test, `demo`, or this skill's own smokes, and one real network call is made per
issue-referencing task, so `--with-gh` is a `plan`-time decision, not something to add reflexively.
It does not help every repo: when a squash-merge subject's `(#N)` is a pull-request number with
no underlying issue at all, there is no issue text to fetch either way, and `--with-gh` cannot
invent one. Every real-world failure — `gh` missing from PATH, not authenticated, the number
resolving to a pull request, the issue not found/private/rate-limited, an unparseable response
— degrades to the same commit-message statement and label, plus a note naming what specifically
happened; a task's statement is never left empty or invented. The plan card surfaces the
outcome as `gh enrichment: N/M task(s) used real issue text`, and — because PRs are the
dominant reason enrichment falls short on squash-merge repos — adds `(K were pull requests)`
whenever any were, e.g. `gh enrichment: 3/10 task(s) used real issue text (7 were pull
requests)`. **Read this number before trusting a verdict on a repo benchmarked with
`--with-gh`**: a low ratio dominated by pull requests means most statements are still commit
messages, weaker evidence than the label alone might suggest.

**`--with-gh` REQUIRES `--gh-repo OWNER/NAME`.** `gh api repos/<owner>/<name>/issues/<N>` with
no explicit owner/name resolves `{owner}`/`{repo}` placeholders from the CURRENT WORKING
DIRECTORY, not from `--repo`/the target being benchmarked — the normal case is running this
tool from the plugin repo against a target elsewhere, so an unset `--gh-repo` makes every
lookup silently query the wrong project. That failure mode is uniquely dangerous here: it does
not error loudly, it degrades to the same commit-message fallback every other `gh` failure
uses, so a wrong-repo run reports something that reads exactly like a real measurement (e.g. a
confident `gh enrichment: 0/10`) while having measured nothing. So `--with-gh` without
`--gh-repo` REFUSES (exit 2) rather than degrading — the one place in this tool where a loud
refusal beats an honest-looking label, because the label would not actually be distinguishable
from a correct result. `--gh-repo` is never inferred from the target's `origin` remote:
`remote`/`config` are not in the read-only git allowlist this tool holds targets to, and
inference would be wrong for a fork anyway — a fork's issues live in the upstream repo, not at
the fork's own remote. Pass the repo you actually want `gh` to query, explicitly, every time.
