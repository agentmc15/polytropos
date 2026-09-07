#!/usr/bin/env python3
"""The one place this repo decides what must not leave a machine in plain text.

WHY IT EXISTS. `journal/inbox.md` is where a person drops meeting notes and to-dos, in their
own words. Those lines were read verbatim into the daily digest, written to disk, and sent to a
cloud model by the summarizer -- while the documentation said "Nothing secret is ever written
to the journal, its logs, or git". That sentence was true only about GIT: a root-anchored
`.gitignore` stops a commit, and stops nothing else. A synthetic credential typed into the
inbox survived persistence and dispatch intact.

WHAT THIS PROMISES, AND WHAT IT CANNOT. It finds strings that MATCH KNOWN CREDENTIAL SHAPES and
replaces them with a label. That is worth doing -- the common accidents are exactly
shape-recognizable, because providers deliberately give their tokens distinctive prefixes -- and
it is emphatically not a guarantee of absence. A password that looks like a word, a customer
name, an unreleased product, an address: none of those have a shape, and none of them are
caught here. Any claim of the form "no secrets can reach X" is false and must not be written on
top of this module. The honest claim is field-level: THESE fields are sent, bounded to THIS
length, with known credential shapes replaced, and the counts are reported so a person can see
that something was caught.

WHAT IT REPORTS. Counts and kinds, never values. A redaction report that quoted what it found
would be a second copy of the secret, in a file that is likelier to be read aloud than the
first one.
"""

import re

#: The label a match is replaced with. Deliberately says WHICH shape matched: a person reading
#: a digest needs to know an AWS key was in their inbox, and must not be shown the key to
#: learn it.
PLACEHOLDER = "[redacted:{kind}]"

#: Credential shapes, specific before generic. Each is a published token format or a
#: universally recognized assignment; nothing here is a guess about what a secret "looks like".
PATTERNS = (
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws-access-key-id", re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("github-token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("slack-token", re.compile(r"\bxox[baprse]-[A-Za-z0-9\-]{10,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
    ("bearer-token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/\-]{16,}=*")),
    ("basic-auth-url", re.compile(r"\b[a-z][a-z0-9+.\-]*://[^\s/:@]+:[^\s/@]+@")),
    # An explicit assignment to a secret-shaped NAME. This is the one that catches the
    # home-grown cases -- `db_password = hunter2` has no distinctive value shape, only a
    # distinctive key.
    ("assigned-secret", re.compile(
        # The leading `[A-Za-z0-9_.-]*?` is load-bearing: `db_password` has no word boundary
        # before `pass`, because `_` is a word character -- so a plain `\b` misses every
        # prefixed name, which is most of the real ones.
        r"(?i)\b[A-Za-z0-9_.\-]*?"
        r"(?:pass(?:word|wd)?|secret|token|api[_-]?key|access[_-]?key|"
        r"private[_-]?key|client[_-]?secret|credential)s?\b\s*[:=]\s*\S+"
    )),
)

#: Longest a single retained field may be. Bounding is separate from redacting and matters on
#: its own: an unbounded field is an unbounded disclosure, however clean it looks.
DEFAULT_FIELD_LIMIT = 500

#: Appended when a field is cut, so a reader can tell "short" from "shortened".
TRUNCATION_NOTE = "… [truncated {dropped} chars]"


def scan(text, patterns=PATTERNS):
    """Kinds of credential shape present in `text`, as `{kind: count}`. Never the values."""
    found = {}
    remaining = text or ""
    for kind, pattern in patterns:
        matches = pattern.findall(remaining)
        if matches:
            found[kind] = found.get(kind, 0) + len(matches)
            remaining = pattern.sub(PLACEHOLDER.format(kind=kind), remaining)
    return found


def redact(text, limit=DEFAULT_FIELD_LIMIT, patterns=PATTERNS):
    """`text` with known credential shapes labelled and its length bounded.

    Returns `{"text", "redactions", "truncated", "original_length"}`. `redactions` is
    `{kind: count}` -- enough for a person to see that something was caught, and never enough
    to reconstruct it.

    Redaction happens BEFORE truncation on purpose: cutting first could leave the tail of a
    key in the retained half, where nothing would match it any more.
    """
    original = text or ""
    result = original
    redactions = {}
    for kind, pattern in patterns:
        result, count = pattern.subn(PLACEHOLDER.format(kind=kind), result)
        if count:
            redactions[kind] = redactions.get(kind, 0) + count
    truncated = False
    if limit is not None and len(result) > limit:
        dropped = len(result) - limit
        result = result[:limit] + TRUNCATION_NOTE.format(dropped=dropped)
        truncated = True
    return {
        "text": result,
        "redactions": redactions,
        "truncated": truncated,
        "original_length": len(original),
    }


def redact_all(items, limit=DEFAULT_FIELD_LIMIT, patterns=PATTERNS):
    """Redact a sequence of strings -> `(texts, report)`.

    `report` totals what happened across the whole set: `{"redactions": {kind: count},
    "truncated": n, "items": n}`. It is the inspectable summary a caller shows a person before
    anything is persisted or dispatched.
    """
    texts = []
    totals = {}
    truncated = 0
    for item in items:
        outcome = redact(item, limit=limit, patterns=patterns)
        texts.append(outcome["text"])
        for kind, count in outcome["redactions"].items():
            totals[kind] = totals.get(kind, 0) + count
        truncated += 1 if outcome["truncated"] else 0
    return texts, {"redactions": totals, "truncated": truncated, "items": len(texts)}


def describe(report):
    """One human line for a redaction report, or "" when it found nothing worth saying."""
    parts = []
    kinds = report.get("redactions") or {}
    if kinds:
        detail = ", ".join(f"{count}× {kind}" for kind, count in sorted(kinds.items()))
        parts.append(f"redacted {detail}")
    if report.get("truncated"):
        parts.append(f"{report['truncated']} field(s) truncated")
    if not parts:
        return ""
    return (
        "; ".join(parts)
        + " — shape-matching only, which cannot prove no secret remains"
    )


def _cli(argv=None):
    """`redact.py [file]` -- redact stdin or a file, and report what was caught on stderr."""
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)
    text = open(argv[0], encoding="utf-8").read() if argv else sys.stdin.read()
    outcome = redact(text, limit=None)
    sys.stdout.write(outcome["text"])
    line = describe({"redactions": outcome["redactions"], "truncated": 0})
    if line:
        print(line, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
