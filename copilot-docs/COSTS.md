# Costs and AIC accounting

This center answers cost questions honestly by keeping several different kinds of number
strictly separate and by deriving every unit and rate from data at the moment it is needed —
this page never states a live conversion, rate, or allowance as prose.

## Three different questions

"What will this cost?" is actually at least three different questions, each answered by a
different tool, and this repository never blends their answers into one figure:

1. **A prospective task estimate** — "if I ran one task of roughly this size on this model, what would it cost?" Answered by `python3 bin/copilot_pricing.py est <PROFILE> <MODEL_ID>`, entirely from the pricing data, before any real work happens.
2. **A historical usage-log estimate** — "what have I actually spent so far?" Answered by `python3 bin/copilot_usage.py`, read strictly from local session logs after the fact. This is an accounting of the past, not a forecast.
3. **A prospective per-document authoring estimate** — "if this documentation center's Markdown were authored fresh by a model, what would that cost?" Answered by this center's own generated `AIC-REPORT.md`, computed the same way as question 1 but applied to each document in the manifest instead of to an arbitrary task.

None of the three is derived from either of the others, and none of them is a bill.

## The AIC unit

AI Credits (AIC) are this repository's own accounting unit, defined entirely by
`data/pricing.copilot.json`'s billing-unit data — its USD-per-credit value, like every other
rate on this page, is a runtime fact you read from the pricing engine, never a number typed here.
Run `python3 bin/copilot_pricing.py prefs` or `models --json` to see the currently active
figures; if this page and the live pricing data ever seem to disagree, the live data is correct
and this page is stale.

## How the pricing engine works, in general terms

Every estimate in this repository — prospective, per-document, or a runway projection — is
computed by the same engine, `bin/copilot_pricing.py`'s `est_cost`, from the same source file. In
general terms, without naming a literal value:

- An estimate takes a **task-size profile** (assumed input and output token counts) and a **model id**, and returns a USD figure and its AIC equivalent.
- Some models get a lower rate on **cached** input tokens than on fresh input tokens; the engine, not this page, decides which cache-hit assumption applies and how much that changes the result.
- The engine may attach **warnings** to a result — for example a long-context step-up or a promotional-pricing window tied to the pricing data's own effective date — and those warnings are computed at estimate time, not asserted here.
- `python3 bin/copilot_pricing.py runway <PLAN> <PROFILE> <MODEL_ID>` projects how far a plan's monthly AIC allowance stretches for repeated tasks of one size on one model; `<PLAN>` is a plan id from the pricing data, exactly like `<PROFILE>` and `<MODEL_ID>` are profile and model keys from the same data.

## Historical usage honesty

`bin/copilot_usage.py` reads local session-state event logs and is deliberately conservative
about what it claims to know precisely:

- Copilot's own event logs record a full input/cache/output token split only at the *session* level, attributed to that session's **last** model — for a session that used more than one model, that split-by-model attribution is an **approximation**, not an exact per-model accounting.
- The report's separate **per-turn, output-tokens-only** table is the **exact** cross-model slice: it comes straight from each turn's own recorded output-token count, with no last-model approximation involved, at the cost of leaving input and cached-input tokens out of that view.
- A session that crashed or is still open, with no recorded shutdown token details, degrades to that output-only view for its entire tally — its input and cached-input tokens are reported as unpriced, and its total is therefore an **undercount**, never a fabricated estimate of the missing pieces.
- Copilot's own reported consumption unit is **AIU** (AI Usage units), not AIC. The report shows Copilot's AIU figure as a cross-check alongside its own AIC estimate, and the two are never treated as equal or convertible into one another.

## Proxy honesty

Some figures elsewhere in this repository (for example a subscription-billed harness's
API-equivalent or relative-burn estimate) are explicitly labeled **proxies**: an illustrative
comparison figure, not a real invoice line. A proxy dollar or AIC figure is never merged into a
billed total, never presented without its label, and never treated as authoritative over an
actual bill.

## Exact document accounting policy

Every Markdown and HTML document declared in `manifest.json`, plus this center's own generated
report artifacts, gets exactly one row in `aic-report.json` (rendered by `AIC-REPORT.md`), under
one fixed accounting policy:

- **Measured, not assumed:** for each document, the generator records its whole-file UTF-8 byte count, its Unicode word count, and a stdlib lexical-token approximation — never a vendor-specific tokenizer claim.
- **Generated blocks are excluded from the AI-output count:** the lexical measurement used as a stand-in for a document's *AI-authored* output specifically excludes the text inside every `<!-- BEGIN/END GENERATED -->` marker pair, so deterministic roster/table expansion is never mistaken for authored prose.
- **Assumed input is a declared profile, not telemetry:** each authored Markdown document declares one symbolic input profile in the manifest; the actual input-token count for that profile is read from the pricing data's task profiles at report time, representing an assumed reading/prompt context, not a measurement of any real prompt.
- **The priced model is prefs-resolved:** each document's manifest tier resolves through the active preference snapshot exactly like everywhere else in this bundle — never a model id hardcoded into the report logic.
- **The cost formula is the existing `est_cost`, not a copy:** the report adds one ephemeral, in-memory task profile (using the assumed input tokens and the measured AI-output lexeme count as its output tokens) and calls the same pricing engine used everywhere else — no duplicated rate arithmetic anywhere in the report path.
- **Markdown gets the estimate; HTML gets zero:** an authored Markdown document with an `"estimated"` authoring mode receives a prospective authoring cost. Its HTML companion is a deterministic local render of that same Markdown — its authoring AIC and render AIC are both zero, and its row points back at its Markdown source instead of repeating the estimate.
- **Report artifacts are zero:** `AIC-REPORT.md`, `aic-report.html`, and `aic-report.json` themselves carry zero cost, since they are deterministic renderings of the report's own data rather than authored content — their measured-size fields are `n/a` with an explicit self-reference note, since a document's own byte size does not exist yet while it is being generated.
- **Totals are authored-Markdown-only:** the report's totals sum only the estimated Markdown documents' costs — HTML rows and report-artifact rows never contribute to the total, so nothing is ever double-counted between a document and its own HTML rendering.
- **Uncertainty is stated, not hidden:** every estimated row carries an explicit note that it is a prospective estimate built from a declared convention and a measured stand-in for output tokens — not a historical usage measurement of any real authoring session.

## Regenerating

Everything on this page and in the linked report is reproducible from the current pricing and
preference data with:

```bash
python3 bin/copilot_docs.py build
python3 bin/copilot_docs.py check
python3 bin/copilot_docs.py report
```

`build` writes the refreshed generated blocks, HTML, and report under `copilot-docs/`; `check` is
read-only and fails on any drift against the recorded snapshot; `report` prints a live,
personalized prospective report to stdout without writing anything.

## The generated report

See [`AIC-REPORT.md`](AIC-REPORT.md) (also available as
[`aic-report.html`](aic-report.html)) for the full, generated, per-document table this page
describes, and [`aic-report.json`](aic-report.json) for its machine-readable source of truth.
