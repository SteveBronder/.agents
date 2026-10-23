#!/usr/bin/env python3
"""Check markdown files against the mechanical rules of the plain-style guide.

Only rules that a regex can check reliably live here. The rest of the guide
(references/style_guide.md) needs a careful read by a person or a model.

Usage:
    check_style.py FILE [FILE ...] [--max-words N] [--skip-quoted]
                   [--ignore RULE] [--json]
    check_style.py --list-rules

Exit status is 1 when any error is found, 2 on a usage or file problem, and
0 otherwise. Warnings alone do not fail the run.
"""
from __future__ import annotations

import argparse
import bisect
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

# rule id -> (severity, section of the style guide, what the rule checks)
RULES = {
    "semicolon": ("error", "Punctuation", "Semicolons anywhere, including headings and tables."),
    "sentence-length": ("error", "Rule 16", "Sentences longer than --max-words words (default 40)."),
    "for-every": ("error", "Rule 19", 'The "for every" completeness flourish.'),
    "jargon": ("error", "Other patterns", '"sits inside", "cadence", "rides along".'),
    "candor": ("error", "Rule 4", 'Comments on the writer\'s own frankness ("frankly", "to be clear").'),
    "callout": ("error", "Structure", "Callout boxes and admonitions (> [!NOTE], !!! note, ::: note)."),
    "non-ascii": ("error", "Punctuation", "Any non-ASCII character, anywhere in the file (emoji included)."),
    "figurative-verb": ("warning", "Rule 18", '"flows into", "carries through", "enters the work".'),
    "and-its": ("warning", "Rule 15", 'The short "X and its Y" / "with its Y" back-reference.'),
    "pitch-connective": ("warning", "Rule 7", '"so that" and "which means" clauses that justify a choice.'),
    "orientation": ("warning", "Commitments and detail", 'Orientation sentences such as "This section describes".'),
}

# Rules from the guide that need judgment, listed by --list-rules.
UNCHECKED = (
    "Rules 1-3, 5, 6, 8-14, 17 and 18 (beyond the figurative verbs above), "
    "and the Voice, Claims, Structure and Commitments sections."
)

PHRASE_RULES = [
    ("jargon", r"\b(?:sits?|sitting|sat) inside\b",
     '"sits inside" is snappy jargon. Use "is part of".'),
    ("jargon", r"\bcadences?\b",
     '"cadence" is consultant jargon. Use "schedule" or say how often.'),
    ("jargon", r"\b(?:rides?|riding|rode|ridden) along\b",
     '"rides along" is snappy jargon. Use "accompanies".'),
    ("figurative-verb", r"\b(?:flows?|flowed|flowing) into\b",
     "Figurative verb. Use a plain one."),
    ("figurative-verb", r"\b(?:carry|carries|carried|carrying) through\b",
     "Figurative verb. Use a plain one."),
    ("figurative-verb", r"\b(?:enters?|entered|entering) the work\b",
     "Figurative verb. Use a plain one."),
    ("for-every", r"\bfor every\b",
     'Completeness flourish. Say it plainly ("with sources", "each task has a fixed price").'),
    ("and-its", r"\b(?:and|with) (?:its|their)\b",
     'Back-reference with "its"/"their". Keep it only if the sentence needs it.'),
    ("candor", r"\b(?:frankly|candidly|honestly|to be (?:candid|frank|honest|clear)"
               r"|let(?: us|'s|\u2019s) be (?:clear|honest|frank)|we say so directly)\b",
     "Comment on the writer's own candor. State the fact and stop."),
    ("pitch-connective", r"\b(?:so that|which means)\b",
     "Possible pitch. Check whether the clause sells the design instead of describing it."),
    ("orientation", r"\b(?:this|the following|the next) (?:sub)?(?:section|chapter|document|report|memo|note)s? "
                    r"(?:describes?|covers?|presents?|explains?|outlines?|discusses|summari[sz]es)\b",
     "Orientation sentence. Cut it if it adds nothing."),
    ("orientation", r"\bsections? \d+(?:\.\d+)*\s*(?:to|through|and|-|\u2013)\s*\d+(?:\.\d+)* "
                    r"(?:describe|cover|present|explain|outline|discuss)",
     "Orientation sentence. Cut it if it adds nothing."),
]
PHRASE_RULES = [(rule, re.compile(rx, re.IGNORECASE), msg) for rule, rx, msg in PHRASE_RULES]

FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
TABLE_RE = re.compile(r"^\s*\|")
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
QUOTE_RE = re.compile(r"^\s*(?:>\s?)+")
LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
HR_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
LINK_DEF_RE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*\S+")
CALLOUT_RE = re.compile(r"^\s*(?:>\s*\[![A-Za-z]+\]|!!!\s*\w|\?\?\?\+?\s*\w|:{3,}\s*\{?\.?\w)")
ICON_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B50\u2B55\u2705\u274C]")

# Suggested ASCII replacements for common non-ASCII characters.
ASCII_HINTS = {
    "\u2018": "use '", "\u2019": "use '", "\u201a": "use '", "\u201b": "use '",
    "\u2032": "use '", "\u201c": 'use "', "\u201d": 'use "', "\u201e": 'use "', "\u2033": 'use "',
    "\u2010": 'use "-"', "\u2011": 'use "-"', "\u2012": 'use "-"', "\u2013": 'use "-"', "\u2212": 'use "-"',
    "\u2014": "rewrite with a comma, parentheses, or two sentences",
    "\u2015": "rewrite with a comma, parentheses, or two sentences",
    "\u2026": 'use "..."', "\u2022": 'use "-" for a list item', "\u00b7": "rewrite without it",
    "\u2192": 'use "->"', "\u2190": 'use "<-"', "\u2194": 'use "<->"', "\u21d2": 'use "=>"',
    "\u00d7": 'use "x"', "\u2264": 'use "<="', "\u2265": 'use ">="', "\u2260": 'use "!="',
    "\u2248": 'use "~" or "about"', "\u00b1": 'use "+/-"', "\u00b0": 'use "degrees"',
    "\u00a0": "use a plain space", "\ufeff": "byte order mark. Delete it",
}

INLINE_SUBS = [
    (re.compile(r"(`+).*?\1"), " "),                      # inline code
    (re.compile(r"!\[([^\]]*)\]\([^)]*\)"), r"\1"),       # images
    (re.compile(r"\[([^\]]+)\]\([^)]*\)"), r"\1"),        # inline links
    (re.compile(r"\[([^\]]+)\]\[[^\]]*\]"), r"\1"),       # reference links
    (re.compile(r"<https?://[^>]+>"), " "),               # autolinks
    (re.compile(r"https?://\S+"), " "),                   # bare URLs
    (re.compile(r"&#?\w+;"), " "),                        # HTML entities
    (re.compile(r"</?[A-Za-z][^>]*>"), " "),              # HTML tags
    (re.compile(r"\*+"), ""),                             # emphasis markers
]
QUOTED_RE = re.compile(r'"[^"]*"|\u201c[^\u201d]*\u201d')

ABBREV_RE = re.compile(
    r"(?:\b(?:e\.g|i\.e|etc|vs|cf|al|approx|Dr|Mr|Mrs|Ms|Prof|St|Fig|Eq|Sec|Inc|Ltd|Jr|Sr|U\.S)"
    r"|\b[A-Z])$"
)
SENT_END_RE = re.compile(r"[.!?]+[\"'\u201d\u2019)\]*_]*")
SENT_START_CHARS = "\"'(\u201c[*_`"
WORD_RE = re.compile(r"[A-Za-z0-9][\w'\u2019.\-]*")


@dataclass
class Finding:
    path: str
    line: int
    rule: str
    severity: str
    guide: str
    message: str
    snippet: str


@dataclass
class Block:
    kind: str  # "prose", "heading" or "table"
    first_line: int
    text: str = ""
    line_starts: list = field(default_factory=list)

    def add(self, line: str) -> None:
        if self.text:
            self.text += " "
        self.line_starts.append(len(self.text))
        self.text += line

    def line_at(self, offset: int) -> int:
        return self.first_line + bisect.bisect_right(self.line_starts, offset) - 1


def clean_inline(line: str) -> str:
    for rx, repl in INLINE_SUBS:
        line = rx.sub(repl, line)
    return line


def parse_blocks(lines: list[str], skip_quoted: bool) -> tuple[list[Block], list[int]]:
    """Split markdown into prose, heading and table blocks.

    Code, front matter, HTML comments and link definitions are dropped.
    Returns the blocks and the line numbers of callout markers.
    """
    blocks: list[Block] = []
    callouts: list[int] = []
    cur: Block | None = None
    cur_quote = False
    fence = None
    in_comment = False
    start = 0

    if lines and lines[0].strip() == "---":
        for j in range(1, len(lines)):
            if lines[j].strip() in ("---", "..."):
                start = j + 1
                break

    def flush():
        nonlocal cur
        if cur is not None and cur.text.strip():
            blocks.append(cur)
        cur = None

    for idx in range(start, len(lines)):
        lineno = idx + 1
        line = lines[idx]

        if fence:
            m = FENCE_RE.match(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) \
                    and not line.strip()[len(m.group(1)):].strip():
                fence = None
            continue
        m = FENCE_RE.match(line)
        if m:
            flush()
            fence = m.group(1)
            continue

        if in_comment:
            if "-->" not in line:
                continue
            line = line.split("-->", 1)[1]
            in_comment = False
        line = re.sub(r"<!--.*?-->", " ", line)
        if "<!--" in line:
            line = line.split("<!--", 1)[0]
            in_comment = True

        if CALLOUT_RE.match(line):
            callouts.append(lineno)

        if not line.strip() or HR_RE.match(line) or LINK_DEF_RE.match(line):
            flush()
            continue

        if HEADING_RE.match(line):
            flush()
            block = Block("heading", lineno)
            block.add(clean_inline(HEADING_RE.sub("", line).rstrip("# \t")))
            blocks.append(block)
            continue

        if TABLE_RE.match(line):
            flush()
            if not TABLE_SEP_RE.match(line):
                block = Block("table", lineno)
                block.add(clean_inline(line))
                blocks.append(block)
            continue

        is_quote = bool(QUOTE_RE.match(line))
        if is_quote:
            if skip_quoted:
                flush()
                continue
            line = QUOTE_RE.sub("", line)
            if not line.strip():
                flush()
                continue

        if LIST_RE.match(line):
            flush()
            line = LIST_RE.sub("", line)
        elif cur is not None and is_quote != cur_quote:
            flush()

        if cur is None:
            cur = Block("prose", lineno)
            cur_quote = is_quote
        cur.add(clean_inline(line.strip()))

    flush()
    return blocks, callouts


def blank_quotes(text: str) -> str:
    """Replace quoted spans with spaces of the same length so offsets survive."""
    return QUOTED_RE.sub(lambda m: " " * len(m.group(0)), text)


def sentences(text: str):
    """Yield (start, end) spans of sentences in a block of prose."""
    start = 0
    for m in SENT_END_RE.finditer(text):
        end = m.end()
        rest = text[end:]
        if rest and not rest[0].isspace():
            continue  # "2.2", "e.g.," and the like
        nxt = rest.lstrip()[:1]
        if nxt and not (nxt.isupper() or nxt.isdigit() or nxt in SENT_START_CHARS):
            continue
        if m.group(0).startswith(".") and ABBREV_RE.search(text[start:m.start()]):
            continue
        if text[start:end].strip():
            yield start, end
        start = end
    if text[start:].strip():
        yield start, len(text)


def snippet(text: str, start: int, end: int, pad: int = 30) -> str:
    lo, hi = max(0, start - pad), min(len(text), end + pad)
    out = text[lo:hi].strip()
    return ("..." if lo > 0 else "") + out + ("..." if hi < len(text) else "")


def non_ascii_message(ch: str, count: int) -> str:
    code = f"U+{ord(ch):04X}"
    name = unicodedata.name(ch, "")
    if ch in ASCII_HINTS:
        hint = ASCII_HINTS[ch]
    elif ICON_RE.match(ch):
        hint = "icon or emoji. Remove it"
    elif unicodedata.category(ch) == "Zs":
        hint = "use a plain space"
    elif unicodedata.category(ch) in ("Cf", "Cc"):
        hint = "invisible character. Delete it"
    else:
        base = unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode()
        hint = f'use "{base}"' if base.strip() else "no ASCII equivalent. Rewrite without it"
    times = f" ({count} on this line)" if count > 1 else ""
    return f"Non-ASCII character {code} {name}{times}. {hint[0].upper() + hint[1:]}."


def check_text(path: str, lines: list[str], max_words: int = 40,
               skip_quoted: bool = False, ignore=()) -> list[Finding]:
    blocks, callouts = parse_blocks(lines, skip_quoted)
    findings: list[Finding] = []

    def add(rule, line, message, snip):
        if rule in ignore:
            return
        severity, guide, _ = RULES[rule]
        findings.append(Finding(path, line, rule, severity, guide, message, snip))

    for lineno in callouts:
        add("callout", lineno, "Callout box. Write the point as ordinary prose.",
            lines[lineno - 1].strip())

    # Non-ASCII is checked on the raw lines, code and front matter included.
    for lineno, raw in enumerate(lines, 1):
        first_col: dict[str, int] = {}
        for col, ch in enumerate(raw):
            if ord(ch) > 127 and ch not in first_col:
                first_col[ch] = col
        for ch, col in first_col.items():
            add("non-ascii", lineno, non_ascii_message(ch, raw.count(ch)), snippet(raw, col, col + 1))

    for block in blocks:
        text = blank_quotes(block.text) if skip_quoted else block.text

        for m in re.finditer(";", text):
            add("semicolon", block.line_at(m.start()),
                "Semicolon. Split the sentence or use a conjunction.",
                snippet(text, m.start(), m.end()))


        for rule, rx, msg in PHRASE_RULES:
            for m in rx.finditer(text):
                add(rule, block.line_at(m.start()), msg, snippet(text, m.start(), m.end()))

        if block.kind == "prose":
            for s, e in sentences(text):
                n = len(WORD_RE.findall(text[s:e]))
                if n > max_words:
                    sent = text[s:e].strip()
                    lead = len(text[s:e]) - len(text[s:e].lstrip())
                    add("sentence-length", block.line_at(s + lead),
                        f"Sentence has {n} words (limit {max_words}). Split it at a clause boundary.",
                        sent if len(sent) <= 90 else sent[:87] + "...")

    findings.sort(key=lambda f: (f.line, f.rule))
    return findings


def check_file(path: Path, **kwargs) -> list[Finding]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return check_text(str(path), lines, **kwargs)


def list_rules() -> None:
    width = max(map(len, RULES))
    for rule, (severity, guide, desc) in RULES.items():
        print(f"{rule:<{width}}  {severity:<7}  {guide:<22}  {desc}")
    print(f"\nNot checked (read for these): {UNCHECKED}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check markdown files against the plain-style guide.")
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--max-words", type=int, default=40, help="sentence length limit (default 40)")
    ap.add_argument("--skip-quoted", action="store_true",
                    help="ignore text in double quotes and blockquotes")
    ap.add_argument("--ignore", action="append", default=[], metavar="RULE",
                    help="rule id to skip (repeatable)")
    ap.add_argument("--json", action="store_true", help="print findings as JSON")
    ap.add_argument("--list-rules", action="store_true", help="list the checked rules and exit")
    args = ap.parse_args(argv)

    if args.list_rules:
        list_rules()
        return 0
    if not args.files:
        ap.error("no files given")
    unknown = set(args.ignore) - set(RULES)
    if unknown:
        ap.error(f"unknown rule(s) for --ignore: {', '.join(sorted(unknown))}")

    findings: list[Finding] = []
    for path in args.files:
        try:
            findings += check_file(path, max_words=args.max_words,
                                   skip_quoted=args.skip_quoted, ignore=set(args.ignore))
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{path}: {exc}", file=sys.stderr)
            return 2

    errors = sum(f.severity == "error" for f in findings)
    warnings = len(findings) - errors
    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        for f in findings:
            print(f"{f.path}:{f.line}: {f.severity} [{f.rule}, {f.guide}] {f.message} | {f.snippet}")
        print(f"{errors} error(s), {warnings} warning(s) in {len(args.files)} file(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
