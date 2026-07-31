---
name: journal
description: Generate the daily work journal — collect today's AI usage across Claude Code, Copilot CLI, and Codex CLI plus git activity into a digest, then write the narrative, technical, and next-day-plan summaries. Use when the user asks for their work journal, daily summary, "what did I do today", or to plan tomorrow.
---

You produce the user's daily work journal from local, read-only sources. The journal engine is
harness-agnostic — it already reads Claude Code, Copilot CLI, and Codex CLI history — so the
journal you produce here is the same cross-harness journal any of the three surfaces would make.

## Collect the digest

Run the collector to build today's digest deterministically:

```bash
python3 {{POLYTROPOS_ROOT}}/bin/journal_collect.py --print
```

Flags (the real argparse surface — do not invent others): `--date YYYY-MM-DD` for a specific
day (default: today), `--repo PATH` to add a git repo to scan (repeatable), `--journal-dir DIR`
to point elsewhere. The collector is cheap, model-free, and strictly read-only over the three
homes — it never calls a model and never touches the network. It writes only under the
gitignored `journal/<date>/` directory (`digest.json`), nowhere else.

## Write the summaries in-session — the ONLY mode from this harness

Print the exact prompts for today's digest without dispatching anything:

```bash
python3 {{POLYTROPOS_ROOT}}/bin/journal_summarize.py --date <date> --dry-run
```

`--dry-run` prints the three prompts (narrative, technical, next-day-plan) and spawns nothing.
Read `journal/<date>/digest.json` for the facts, follow each printed prompt's required headings
exactly, and use digest facts only — no invented details. Write the three documents YOURSELF
(this session is already paid for) to `journal/<date>/narrative.md`, `journal/<date>/technical.md`,
and `journal/<date>/next-day.md`. Then summarize the three documents for the user and link their
paths — don't paste full drafts back into chat.

**Never run `journal_summarize.py` without `--dry-run` from this harness.** Its headless mode
dispatches the Claude CLI to write the documents itself — a cross-harness spend this skill must
never trigger. The two-pass flow above (collect, then print-and-write-yourself) is the only
sanctioned path here.

## Privacy

The digest is metadata-only — project and repo names, commit subjects, kit task titles, and any
inbox text, never transcript or message text. Writing the summaries sends the digest to a model
(this session, in the in-session flow above). Everything the journal produces stays under the
gitignored `journal/` directory.

## Same-named agent

For persona-isolated runs — a separate dispatch that should carry its own model pin
instead of this session's model — use the `journal` custom agent: pick it in the `/agent`
picker, or run `copilot --agent journal -p "<task>"`. This skill and that agent are the
same capability on two surfaces; the agent's frontmatter carries the model pin, this
skill runs on whatever model the session already uses.

## Installed?

If the literal `{{POLYTROPOS_ROOT}}` text is still visible above, the bundle is not
installed — tell the user to run `python3 bin/harness_select.py install --harness copilot`
(then `/skills reload` picks the skills up in-session).
