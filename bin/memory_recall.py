#!/usr/bin/env python3
"""memory-skill budget-capped recall engine (schema_version 1) — the anti-bloat spine.

This tool is STRICTLY READ-ONLY over the store: it reads fact files under ``--memory-dir``
(default ``PLUGIN_ROOT / "memory"``, exactly how ``journal/`` works) via ``memory_store``'s
schema functions and returns only the winners — the corpus never enters model context, only a
block capped by the pinned ``MAX_FACTS`` / ``BUDGET_CHARS`` (PLAN.md D4). The ONLY writes this
tool ever performs live inside ``--demo``'s own ``tempfile.TemporaryDirectory`` (synthetic
facts, thrown away on exit); no real store, no home directory, and no other path on disk is
ever written. This file resolves no per-user home directory anywhere and spawns no child
process of any kind. It prices NOTHING: no pricing file is read, imported, or edited, and no
price or model id appears anywhere below. No network, no ``urllib`` / ``http.client`` /
``socket``.

Ranking is the pure-stdlib lexical BM25-lite of PLAN.md D5; the relevance gate of D6 is allowed
to return NOTHING (an empty recall is a SUCCESS, exit 0 — better nothing than noise). The
schema functions (``load_store``, ``parse_fact``, ``staleness_state``, ``token_set``) are
REUSED from ``bin/memory_store.py``, loaded read-only via ``importlib`` (``bin/`` is not a
package) — never re-implemented here.
"""

import argparse
import importlib.util
import json
import math
import re
import sys
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MEMORY_DIR = PLUGIN_ROOT / "memory"

SCHEMA_VERSION = 1

# ---- pinned constants (PLAN.md D4/D5/D6) — never loosen to make a test pass ---------------
MAX_FACTS = 5
BUDGET_CHARS = 4000
GATE_MIN_SCORE = 1.0
GATE_MIN_TERMS = 2
K_SAT = 1.2
STALE_MULT = 0.6
CONF_MULT = {"high": 1.0, "medium": 0.9, "low": 0.7}
FIELD_WEIGHTS = {"name": 3, "tags": 3, "description": 2, "body": 1}
STOPWORDS = frozenset("a an and are as at be but by for from has have how in is it its of on or that the this to was what when where which who will with you your".split())
GATE_EMPTY_LINE = "no memory above the relevance gate for this query"


def _load(name):
    """Load a sibling ``bin/<name>.py`` module read-only (the journal_collect.py pattern)."""
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parent / f"{name}.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ms = _load("memory_store")  # schema functions reused read-only (load_store, staleness_state, ...)


# --------------------------------------------------------------------------- tokenizing / scoring

def _field_counts(text):
    """Term -> count over ``re.findall(r"[a-z0-9]+", text.lower())``, dropping 1-char tokens
    and STOPWORDS (counts kept — NOT the set helper). Empty/None -> empty Counter."""
    counts = Counter()
    for tok in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if len(tok) > 1 and tok not in STOPWORDS:
            counts[tok] += 1
    return counts


def _query_terms(query):
    """Distinct query terms in first-appearance order (deterministic): the store's ``token_set``
    tokenization (``[a-z0-9]+``, lowercase, drop 1-char) minus STOPWORDS. The resulting SET
    equals ``ms.token_set(query) - STOPWORDS``; order is pinned for stable display/JSON."""
    seen = []
    seen_set = set()
    for tok in re.findall(r"[a-z0-9]+", (query or "").lower()):
        if len(tok) <= 1 or tok in STOPWORDS or tok in seen_set:
            continue
        seen_set.add(tok)
        seen.append(tok)
    return seen


def _last_verified(meta):
    return meta.get("last_verified") or meta.get("created") or ""


def _header_line(slug, meta, state):
    name = meta.get("name", slug)
    ftype = meta.get("type", "")
    confidence = meta.get("confidence", "")
    line = f"### [{slug}] {name} — {ftype}/{confidence}, verified {_last_verified(meta)}"
    if state == "stale":
        line += " — STALE, verify before relying"
    return line


def _render_block(header_line, body):
    """A fact's rendered output block: header line, newline, body. Its length is what the
    budget counts (WHOLE-FACT — a block either lands intact or is dropped entirely)."""
    return f"{header_line}\n{body}"


def recall(memory_dir, query, now, include_expired=False):
    """Read the store and return the gate-surviving facts, sorted (score desc, last_verified
    desc, slug asc) — BEFORE the budget cap. Pure function of the store: no writes, no dispatch.

    Returns a dict: ``query`` (term list), ``survivors`` (list of per-fact dicts),
    ``withheld_expired`` (int), ``notes`` (list), ``store_empty`` (bool).
    """
    facts, notes = ms.load_store(memory_dir)
    terms = _query_terms(query)

    # Partition: expired facts are excluded from recall AND from N/df unless --include-expired.
    corpus = []
    withheld_expired = 0
    for slug, meta, body in facts:
        state = ms.staleness_state(meta, now)
        if state == "expired" and not include_expired:
            withheld_expired += 1
            continue
        corpus.append((slug, meta, body, state))

    n_docs = len(corpus)

    # First pass: per-fact weighted term frequency for each query term + corpus df.
    scored = []
    df = Counter()
    for slug, meta, body, state in corpus:
        fields = {
            "name": meta.get("name", ""),
            "tags": meta.get("tags", ""),
            "description": meta.get("description", ""),
            "body": body,
        }
        field_counts = {f: _field_counts(txt) for f, txt in fields.items()}
        wtf = {}
        for t in terms:
            total = 0
            for f, weight in FIELD_WEIGHTS.items():
                total += weight * field_counts[f].get(t, 0)
            if total > 0:
                wtf[t] = total
        for t in wtf:
            df[t] += 1
        scored.append((slug, meta, body, state, wtf))

    # Second pass: raw BM25-lite score, staleness/confidence multipliers, and the gate.
    survivors = []
    for slug, meta, body, state, wtf in scored:
        raw = 0.0
        for t, weight in wtf.items():
            df_t = df[t]
            idf = math.log(1 + (n_docs - df_t + 0.5) / (df_t + 0.5))
            raw += idf * weight / (weight + K_SAT)
        conf_mult = CONF_MULT.get(meta.get("confidence", ""), CONF_MULT["low"])
        stale_mult = STALE_MULT if state == "stale" else 1.0
        final = raw * stale_mult * conf_mult

        matched_terms = len(wtf)
        tag_tokens = set(re.findall(r"[a-z0-9]+", meta.get("tags", "").lower()))
        tag_hit = any(t in tag_tokens for t in terms)
        gate_terms = matched_terms >= GATE_MIN_TERMS or tag_hit
        if not (gate_terms and final >= GATE_MIN_SCORE):
            continue

        header_line = _header_line(slug, meta, state)
        block = _render_block(header_line, body)
        survivors.append({
            "slug": slug,
            "name": meta.get("name", slug),
            "type": meta.get("type", ""),
            "confidence": meta.get("confidence", ""),
            "state": state,
            "score": final,
            "chars": len(block),
            "body": body,
            "last_verified": _last_verified(meta),
            "header_line": header_line,
            "block": block,
        })

    survivors.sort(key=lambda r: (-r["score"], _neg_date_key(r["last_verified"]), r["slug"]))
    return {
        "query": terms,
        "survivors": survivors,
        "withheld_expired": withheld_expired,
        "notes": notes,
        "store_empty": not facts,
    }


def _neg_date_key(s):
    """Sort key that orders ``last_verified`` DESCENDING while score/slug stay ascending. ISO
    dates sort lexically; invert each char so a plain ascending tuple sort yields date-desc."""
    return tuple(-ord(c) for c in s)


def apply_budget(survivors, max_facts, budget_chars):
    """Select gate survivors in order under the whole-fact budget (PLAN.md D4). Returns
    ``(emitted, dropped)`` where each emitted entry carries a possibly-truncated ``block``.
    Truncation is whole-fact: a fact that would overflow is dropped entirely — EXCEPT the very
    top survivor, whose header is emitted with a pointer line when its body alone overflows."""
    emitted = []
    dropped = 0
    used = 0
    for r in survivors:
        if len(emitted) >= max_facts:
            dropped += 1
            continue
        if used + r["chars"] > budget_chars:
            if not emitted:
                # Top survivor alone exceeds the char budget: header + pointer, never a body.
                pointer = f"(body exceeds budget — read memory/facts/{r['slug']}.md)"
                block = f"{r['header_line']}\n{pointer}"
                trunc = dict(r, block=block, chars=len(block), body="")
                emitted.append(trunc)
                used += len(block)
                continue
            dropped += 1
            continue
        emitted.append(r)
        used += r["chars"]
    return emitted, dropped


# --------------------------------------------------------------------------- rendering

def render_markdown(result, max_facts, budget_chars):
    survivors = result["survivors"]
    if result["store_empty"]:
        return "no memory store yet"
    if not survivors:
        return GATE_EMPTY_LINE

    emitted, dropped = apply_budget(survivors, max_facts, budget_chars)
    total_chars = sum(r["chars"] for r in emitted)
    query_str = " ".join(result["query"])
    lines = [f"## Recalled memory ({len(emitted)} facts, {total_chars} chars, query: {query_str})"]
    for r in emitted:
        lines.append("")
        lines.append(r["block"])
    if dropped:
        lines.append("")
        lines.append(f"(+{dropped} more above the gate — raise --max-facts/--budget-chars "
                      f"or read memory/index.md)")
    if result["withheld_expired"]:
        lines.append("")
        lines.append(f"({result['withheld_expired']} expired fact(s) withheld — "
                      f"memory_store.py review to prune)")
    return "\n".join(lines)


def render_json(result, max_facts, budget_chars):
    emitted, dropped = apply_budget(result["survivors"], max_facts, budget_chars)
    out = {
        "schema_version": SCHEMA_VERSION,
        "query": result["query"],
        "facts": [
            {
                "slug": r["slug"],
                "name": r["name"],
                "type": r["type"],
                "confidence": r["confidence"],
                "state": r["state"],
                "score": round(r["score"], 4),
                "chars": r["chars"],
                "body": r["body"],
            }
            for r in emitted
        ],
        "dropped_for_budget": dropped,
        "withheld_expired": result["withheld_expired"],
        "notes": result["notes"],
    }
    return json.dumps(out, indent=2)


# --------------------------------------------------------------------------- demo (byte-stable)

DEMO_NOW = "2026-01-15"
DEMO_QUERY = "deploy the build to cloudflare workers"


def _demo_write(memory_dir, slug, name, ftype, confidence, tags, created, last_verified,
                expires, description, body):
    meta = {
        "schema": str(ms.SCHEMA_VERSION),
        "name": name,
        "description": description,
        "type": ftype,
        "tags": tags,
        "created": created,
        "last_verified": last_verified,
        "expires": expires,
        "confidence": confidence,
        "source": "demo (synthetic)",
    }
    path = ms.fact_path(memory_dir, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ms.render_fact(meta, body))


def _build_demo_store(memory_dir):
    _demo_write(memory_dir, "editor-prefs", "Editor preferences", "user", "high",
                "editor, formatting", "2026-01-10", "2026-01-10", "never",
                "How the editor is configured",
                "Two-space indentation and a trailing newline on save.")
    _demo_write(memory_dir, "deploy-target", "Deploy target", "reference", "high",
                "deploy, cloudflare", "2026-01-10", "2026-01-10", "never",
                "Where we deploy the app",
                "Deploy to Cloudflare Workers via wrangler.")
    _demo_write(memory_dir, "legacy-build-flow", "Legacy build flow", "project", "medium",
                "build, deploy", "2025-09-01", "2025-09-01", "never",
                "The old build and deploy steps",
                "The legacy build ran make then deploy scripts.")
    _demo_write(memory_dir, "deprecated-endpoint", "Deprecated endpoint", "reference", "low",
                "deploy, api", "2025-06-01", "2025-06-01", "2025-12-31",
                "Old deploy API endpoint",
                "The old deploy endpoint is gone.")
    _demo_write(memory_dir, "favorite-color", "Favorite color", "user", "high",
                "preference", "2026-01-10", "2026-01-10", "never",
                "A personal preference",
                "The favorite color is teal.")
    _demo_write(memory_dir, "test-runner-choice", "Test runner choice", "project", "high",
                "tests, unittest", "2026-01-10", "2026-01-10", "never",
                "Which test runner the suite uses",
                "Use unittest for the suite.")


def run_demo():
    lines = [
        "memory_recall.py --demo — every fact below is SYNTHETIC, written to a throwaway "
        "temp dir; nothing real is read or written.",
        "",
        f"Query: {DEMO_QUERY!r}   (--now {DEMO_NOW})",
        "",
    ]
    with tempfile.TemporaryDirectory() as tmp:
        _build_demo_store(tmp)

        lines.append("== Run A: defaults — relevance gate + stale marker + expired withheld ==")
        result_a = recall(tmp, DEMO_QUERY, DEMO_NOW, include_expired=False)
        lines.append(render_markdown(result_a, MAX_FACTS, BUDGET_CHARS))
        lines.append("")
        lines.append("== Run B: --max-facts 1 — budget cap drops a gate survivor ==")
        result_b = recall(tmp, DEMO_QUERY, DEMO_NOW, include_expired=False)
        lines.append(render_markdown(result_b, 1, BUDGET_CHARS))
    print("\n".join(lines))
    return 0


# --------------------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Budget-capped, relevance-gated memory recall (stdlib-only, read-only).")
    ap.add_argument("--query", default=None, help="5-15 salient keywords from the task at hand")
    ap.add_argument("--memory-dir", default=str(DEFAULT_MEMORY_DIR))
    ap.add_argument("--max-facts", type=int, default=MAX_FACTS)
    ap.add_argument("--budget-chars", type=int, default=BUDGET_CHARS)
    ap.add_argument("--include-expired", action="store_true",
                    help="include expired facts in recall AND corpus stats (review flows)")
    ap.add_argument("--now", default=date.today().isoformat(),
                    help="YYYY-MM-DD (default: today) — all date math flows through this")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--demo", action="store_true",
                    help="run the pinned synthetic demo in a throwaway temp dir")
    args = ap.parse_args(argv)

    if args.demo:
        return run_demo()

    if not args.query:
        ap.error("--query is required (or use --demo)")

    result = recall(args.memory_dir, args.query, args.now,
                    include_expired=args.include_expired)

    if args.json:
        print(render_json(result, args.max_facts, args.budget_chars))
    else:
        print(render_markdown(result, args.max_facts, args.budget_chars))
    return 0


if __name__ == "__main__":
    sys.exit(main())
