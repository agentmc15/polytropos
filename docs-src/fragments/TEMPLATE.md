# Fragment template — the hand-authored half of every skill page

Read this file end to end before writing your first fragment, and keep it open while you
write. It is the single source the whole fragment set follows; a fragment that disagrees
with it is wrong even if it reads well.

A **fragment** is the only hand-authored content on a generated page. Everything else on a
skill page is derived by `bin/docs_build.py` from the SKILL.md itself. Fragments live at:

| Fragment | Spliced into | Under the heading |
|---|---|---|
| `skills/<harness>/<name>.md` | `docs-site/skills/<harness>/<name>.md` | `## In practice` |
| `skills/<harness>/index.md` | `docs-site/skills/<harness>/index.md` | `## Using these skills` |
| `parity.md` | `docs-site/skills/index.md` | `## Why the rosters differ` |

Nothing else in this directory is spliced anywhere — this file included.

After editing any fragment, run `python3 bin/docs_build.py build` and commit the
regenerated pages with it. Never hand-edit a page under `docs-site/`.

## What is already on the page before your fragment starts

Know this cold, because it is the single largest source of bad fragments. Above your
`## In practice` heading the reader has *already* seen:

1. The page title (`# <name> — <harness label>`).
2. **The skill's frontmatter `description`, verbatim, as a blockquote.** This is the
   "when to use this" sentence the model itself matches on.
3. A facts block: a GitHub link to the SKILL.md source; an **Also available on** line
   listing the same skill on other harnesses, or `this harness only — see the parity
   matrix`; and — *only when the skill actually ships reference files* — a
   **References shipped with the skill** line. Most skills ship none, and then that line
   is omitted entirely rather than printed empty.

And below your fragment, the reader gets `## The skill card — what the model reads`: the
**entire SKILL.md body**, transformed (leading title stripped, headings demoted one level,
relative links rewritten) with a note saying so and linking the unmodified source.

So the page already answers *"what is this and when does it fire"* twice before your first
sentence, and answers *"what exactly does the model do"* completely after your last one.

### The duplication trap (the rule that decides whether a fragment is good)

**Your fragment gives the human frame. It never restates the description, and it never
paraphrases the card.** On a well-written skill, the card's own opening line already says
what the skill does — a `### What it does` that says it a third time in softer words makes
the first screen of the page redundant three ways.

Write instead for a person who has not decided yet:

- *why they would want this* — the situation they are in when it helps;
- *what changes on their machine* — what gets written, dispatched, spent, or printed;
- *what the card assumes they already know* — the tutorial the tight skill text refuses to
  carry, because a model does not need it and a newcomer does.

A useful self-test: delete your `### What it does` and read the page. If nothing was lost,
you wrote a paraphrase. Rewrite it.

## The six required sections

Every per-skill fragment carries exactly these six `###` headings, in this order, with no
others. Skipping one is not allowed: if a section feels empty for a thin skill, the honest
move is two short sentences, never padding and never invention.

### `### What it does`
Two to four plain-language sentences, no jargon a newcomer lacks. Frame the situation and
the effect, not the mechanism. This is where a harness-only skill can say *why this harness*
in one clause — the page already announces the exclusivity, so explain the reason, never
re-announce the fact.

### `### When to reach for it`
Bullets. Concrete situations, not categories — "you are about to run something that looks
expensive" beats "cost optimization". **At least one bullet must be a "not for…" bullet**,
and it should be a real boundary drawn from the skill's own text (a flag combination the
skill warns against, a job a sibling skill owns, a harness the skill does not serve), not a
throwaway disclaimer.

### `### Worked example`
One realistic invocation and what the user actually sees back, in order. Every command,
flag, subcommand, and file path here **must exist** in that skill's SKILL.md, in the
`bin/` engine it names (read the argparse source), or in the harness doc — nothing
invented, nothing recalled from memory. Prefer showing the *shape* of the output (the line
names, the vocabulary, the verdict words) over inventing plausible values; never fabricate
a number.

### `### Failure modes & fallbacks`
What actually goes wrong, what the skill does about it on its own, and when the reader
should escalate or stop. Quote the skill's own failure vocabulary exactly where it has one
(verdict strings, state names, refusal lines) — those words are what the reader will see on
screen, and several are pinned by tests. Do not soften a refusal into a suggestion.

### `### Cost & safety`
Split it plainly: what is read-only, and what spends money or writes files. Derive it from
the skill's own text and honesty labels — if the card calls a figure a labeled estimate and
never a bill, this section must not say anything firmer. **Never write a dollar figure, a
price ratio, a plan allowance, a model id, or a cached date.** Name tiers, link the pricing
file on GitHub, or show the engine command that prints current numbers.

### `### Related`
Sibling skills and pages, as links, each with a few words saying why a reader would follow
it. Do not restate the generated **Also available on** line — link *different* skills and
the deep dives, not the same skill on another harness.

## Mechanical rules

- **Headings are `###` or deeper. Never `#` or `##`.** The page owns h1 and h2. The
  generator rejects both syntaxes outside code fences — ATX (`#`, `##`) and setext (a text
  line directly over a run of `=` or `-`) — naming your file and exiting 2. A heading
  *inside* a fence is fine, so a worked example may legitimately show markdown source.
- **150–550 words by `wc -w` on the file (scaffolding included), AND at most 450 words of
  prose**, where prose means the file with fenced code blocks and table rows (lines
  starting with `|`) removed. Two ceilings, not one, because a single number made the
  budget the output: a 6-row table costs roughly 90 `wc -w` tokens, about 41 of them
  literal pipe characters carrying no information, so a fragment that legitimately needs a
  table or a four-item enumeration was paying for punctuation out of the same budget as
  its sentences. Measure the first number with
  `wc -w docs-src/fragments/skills/<harness>/<name>.md`; measure the second by stripping
  fenced blocks and `|`-prefixed lines from the same file and counting what's left. Under
  150 total usually means you skipped the tutorial the card refuses to carry; over 450
  prose usually means you started re-explaining the card. **Both ceilings are tight on
  purpose and they bind**: the three pilots measure 450/449/450 `wc -w` total but
  441/438/351 words of prose — comfortably inside both bands with zero rework, which is
  why the two numbers ratify the pilots rather than retrofit them. Budget for both — write
  the six sections, then cut, rather than discovering either limit at the end.
  **Harness-index and parity fragments get 150–700 `wc -w`**, with no prose ceiling — they
  summarize a roster rather than one skill and legitimately run longer.
- **No numbers that go stale.** No prices, ratios, plan allowances, model ids, cached
  dates, or roster counts anywhere in a fragment. Aliases and tier names (`cheap`, `mid`,
  `strong`, `frontier`; `haiku`/`sonnet`/`opus`/`fable` where the skill itself uses them)
  are fine, because they are the skill's own vocabulary and do not carry a value.
- **No fabricated facts.** Every flag, subcommand, path, state name, and invocation form
  traces to the SKILL.md, the named engine's source, or a harness doc. Reading engine
  argparse source is the sanctioned way to learn flags; running an engine that reads a real
  home directory is not.

  **Where a fact may come from.** Every command, flag, subcommand, path, state name, and
  invocation form must trace to a **committed file in this repository**, from this list:

  1. the skill's own `SKILL.md` and any `references/*.md` beside it;
  2. the `bin/` engine the skill names — read the argparse and source; never run an engine
     that reads a real home directory;
  3. any `docs/*.md` — all 24, not only the harness docs (`COPILOT-PARITY.md`,
     `COPILOT-WORKFLOW.md`, `MEMORY-SKILL.md` and the rest are canonical hand-written
     sources under D6);
  4. `README.md` and `SETUP.md`;
  5. `copilot-docs/**` — cite freely, **never edit** (it has its own generator,
     `bin/copilot_docs.py`);
  6. bundle payload under `copilot/.github/` and `codex/` when the fact is about the
     bundle itself.

  Nothing else. Not a vendor's web documentation, not `--help` output you did not read in
  source, not memory of how a CLI behaves. If a fact is not in one of these files, the
  fragment does not state it. **You must be able to name the file and line for any fact a
  reviewer asks about.** Where a generated doc (`copilot-docs/**`, a deep-dive mirror) and
  a `SKILL.md` disagree, the `SKILL.md` wins — it is what actually runs.
- **No dollar figure, in prose or inside a fence.** If a skill card carries a worked cost
  anecdote, state the *lesson* and let the reader read the number on the card below — it
  is on the same page.
- **Claims about a sibling skill are facts too.** Before writing "X covers Y", check X's
  own card or page.
- **Fragments are human-only.** They are never loaded into model context, so they may be
  narrative — but they must never contradict the card, because the card is what actually
  runs.
- Tables, admonitions (`!!! note`), and fenced code blocks all render; use them when they
  carry the content better than prose. `pymdownx.details` (`???`) is available too.

## The link contract — read this before you type a link

**Fragments are spliced byte-verbatim. The generator does not rewrite your links.** A link
that would have been correct in a SKILL.md — `docs/GUIDE.md`, `skills/route/SKILL.md` —
becomes a dangling link on the published site, caught only later by the offline link test.
Write links relative to the *page the fragment lands on*:

From a **per-skill** fragment (`docs-site/skills/<harness>/<name>.md`):

| Target | Write |
|---|---|
| Sibling skill, same harness | `escalate.md` |
| Same harness's index | `index.md` |
| A skill on another harness | `../codex/route.md` |
| Parity matrix | `../index.md` |
| A deep dive | `../../deep-dives/how-it-works.md` |
| Site home | `../../index.md` |
| **Anything else in the repo** | a full `https://github.com/agentmc15/polytropos/blob/main/…` URL |

From a **harness index** fragment (`docs-site/skills/<harness>/index.md`): same as above —
it sits in the same directory.

From the **parity** fragment (`docs-site/skills/index.md`) the base directory is one level
up, so: `claude/route.md`, `copilot/budget.md`, `../deep-dives/codex-harness.md`,
`../index.md` for the site home.

Deep-dive slugs are the lowercased stem of the `docs/*.md` source: `docs/CODEX-HARNESS.md`
→ `../../deep-dives/codex-harness.md`. Anchors are not validated by the link test — the
file target is. Only link pages that already exist in the committed tree.

## A fully-worked example

The skill below is a **fixture, not a real skill**, and every command in it is schematic —
it is here for shape, tone, and density only. The three shipped pilots are the real worked
examples; read one beside this file before writing your first fragment:
`skills/claude/route.md` (rich skill, references, two billing modes),
`skills/copilot/budget.md` (harness-only, honest-measurement heavy), and
`skills/codex/doctor.md` (thin card, safety-heavy, carries a state table).

````markdown
### What it does

You have a widget somewhere in the repo and no idea which of them are stale. This skill
reads them where they already live, prints one line per widget with its state and the
reason for it, and stops there — nothing is rewritten until you ask for it in a second,
explicit step.

### When to reach for it

- A widget you expected to see is missing from the listing, or shows a path from an older
  checkout.
- Before an upgrade, to see what an upgrade would actually touch.
- After moving or re-cloning the repo, when paths recorded at install time may be stale.
- **Not** as a fixer — it never writes. The repair step is a separate command that asks
  first.
- **Not** for widgets outside this repo; the engine takes an explicit root and refuses a
  guessed one.

### Worked example

```bash
python3 bin/<engine>.py check --root . --widget-home <dir>
```

One line per widget, in the engine's own vocabulary:

```
<widget>: <state> — <destination> (<reason>)
```

Read the state column first and the reason second: the reason is what tells you whether a
difference is yours or the tool's. Add `--json` for the same plan as machine-readable
output.

### Failure modes & fallbacks

- **A widget is in an unexpected state.** The engine prints the exact remedy beside it;
  use that line rather than improvising, and re-run the check afterwards.
- **The root cannot be proven.** The skill stops instead of running against a guessed
  path — supply the root explicitly and try again.
- **A widget you edited by hand** is preserved, never overwritten. Merge or rename it
  yourself, then re-run.

### Cost & safety

Checking is read-only: it compares bytes and prints, dispatches no model, and spends
nothing. The repair step is a write and asks for explicit authority before it runs. No
figure appears here — the engine reads its numbers at run time from the pricing file
([`data/pricing.json`](https://github.com/agentmc15/polytropos/blob/main/data/pricing.json)).

### Related

- [update](update.md) — the same question across every harness at once.
- [Deep dive: how it works](../../deep-dives/how-it-works.md) — where widget state comes
  from.
````

## Pre-flight checklist

Before you call a fragment done:

1. All six `###` headings, in order, and no `#`/`##` anywhere outside a fence.
2. 150–550 `wc -w` total, and at most 450 words of prose (fenced blocks and `|`-prefixed
   table rows removed) — 150–700 `wc -w`, no prose ceiling, for a harness-index or parity
   fragment.
3. `### What it does` survives the delete-and-reread test — it is not the description or
   the card's opening in other words.
4. At least one real "not for…" bullet.
5. Every command, flag, path, and state name traced to a source you actually opened, from
   the six-source list above — and you can name the file and line for each.
6. Zero prices, ratios, allowances, model ids, cached dates — and zero dollar figures, in
   prose or inside a fence.
7. Any claim about a sibling skill ("X covers Y") checked against that skill's own card or
   page, not assumed.
8. Every link written against the splice target's directory, and every target exists.
9. `python3 bin/docs_build.py build` run, regenerated pages staged with the fragment, and
   `python3 bin/docs_build.py check` exits 0.

## Considered and declined

- **Collapsing the embedded skill card behind a `???` details block.** `pymdownx.details`
  is enabled, and two orchestration pages carry very large cards, which makes this
  tempting. Declined: the card being plainly visible *is* the page's honesty claim ("this
  is exactly what the model reads"), collapsed text is invisible to a reader's in-page
  browser search, and the theme's table of contents already lets anyone skip the card in
  one click. It would also be a generator change, not a fragment one. The mitigation lives
  here instead: **on a page with a very large card, the fragment must stand alone** — a
  reader who never scrolls past it should still know what the skill does, when to use it,
  and what it costs.
- **A seventh optional section.** Declined: six sections applied uniformly to 39 pages is
  what makes the reference scannable. Anything extra belongs inside one of the six, or in a
  deep dive.
