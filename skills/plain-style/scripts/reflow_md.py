#!/usr/bin/env python3
"""Reflow markdown prose: join hard-wrapped lines and start each sentence on a new line.

Agents often hard-wrap markdown at about 80 columns. This script removes the
newlines that fall inside a paragraph. In sentence mode (the default) it then
puts each sentence on its own line, which renders the same as one long line but
is easier to review and diff. Paragraph mode puts each paragraph on one line.

Indented fenced code blocks (``` or ~~~) are moved to column 0, because many
viewers only highlight a fence that starts the line. A fence inside a list item
ends the list, so the rest of that item moves to column 0 with it. Otherwise a
following paragraph indented four or more spaces would render as code. A fence
inside a blockquote stays in the quote, right after the ">".

Other code blocks, math blocks, tables, headings, HTML, front matter and link
definitions are left as they are. List items and blockquotes are reflowed with
their markers and indentation kept. Hard line breaks (two trailing spaces or a
trailing backslash) are kept.

Usage:
    reflow_md.py FILE                     print the result
    reflow_md.py FILE [FILE ...] -i       rewrite the files in place
    reflow_md.py FILE [FILE ...] --check  exit 1 if any file would change
    reflow_md.py FILE [FILE ...] --diff   print a unified diff
    --mode sentence|paragraph             default: sentence
    --keep-fence-indent                   leave indented code fences where they are
"""
from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_style import sentences  # noqa: E402

FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,}|\$\$)")
ATX_RE = re.compile(r"^ {0,3}#{1,6}(?:\s|$)")
HR_RE = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
SETEXT_RE = re.compile(r"^ {0,3}(?:=+|-+)[ \t]*$")
QUOTE_RE = re.compile(r"^ {0,3}> ?")
LIST_RE = re.compile(r"^( {0,3})([-*+]|\d{1,9}[.)])([ \t]+|$)")
TABLE_SEP_RE = re.compile(r"^ {0,3}\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$")
LINKDEF_RE = re.compile(r"^ {0,3}\[[^\]]+\]:\s*\S")
# HTML blocks follow CommonMark. Raw-text tags (pre, script, style, textarea) end at
# their closing tag, comments at "-->", and the rest at a blank line. Block-level tags
# and comments can interrupt a paragraph. A lone tag on a line can only start a block.
RAW_TAGS = "pre|script|style|textarea"
BLOCK_TAGS = (
    "address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|"
    "details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame|frameset|"
    "h[1-6]|head|header|hr|html|iframe|legend|li|link|main|menu|menuitem|nav|noframes|ol|"
    "optgroup|option|p|param|search|section|summary|table|tbody|td|tfoot|th|thead|title|tr|"
    "track|ul"
)
RAW_OPEN_RE = re.compile(rf"^ {{0,3}}<({RAW_TAGS})(?:[\s>]|$)", re.IGNORECASE)
HTML_INTERRUPT_RE = re.compile(
    rf"^ {{0,3}}(?:<!--|<\?|<![A-Za-z]|<!\[CDATA\[|</?(?:{BLOCK_TAGS})(?:[\s/>]|$))", re.IGNORECASE)
HTML_TAG_LINE_RE = re.compile(r"^ {0,3}</?[A-Za-z][A-Za-z0-9-]*(?:\s+[^<>]*?)?/?>\s*$")

# Marks an output line that must start at column 0 (a lifted code fence and what follows it).
LIFTED = "\x00"

# Spans whose inner text must not be split into sentences.
MASK_RES = [
    re.compile(r"(`+).+?\1"),                                   # code spans
    re.compile(r"\]\([^)]*\)"),                                 # link targets
    re.compile(r"<[^>\n]+>"),                                   # HTML tags, autolinks
    re.compile(r"https?://[^\s<>()]*[^\s<>().,;:!?'\"]"),       # bare URLs
    re.compile(r"\$[^$\n]+\$"),                                 # inline math
]


def indent(line: str) -> int:
    lead = line[:len(line) - len(line.lstrip(" \t"))]
    return len(lead.expandtabs(4))


def dedent(line: str, k: int) -> str:
    if k <= 0:
        return line
    lead = line[:len(line) - len(line.lstrip(" \t"))]
    return " " * max(0, len(lead.expandtabs(4)) - k) + line[len(lead):]


def is_table_start(lines: list[str], i: int) -> bool:
    line = lines[i]
    if line.lstrip().startswith("|"):
        return True
    return ("|" in line and i + 1 < len(lines)
            and "|" in lines[i + 1] and bool(TABLE_SEP_RE.match(lines[i + 1])))


def starts_block(lines: list[str], i: int, in_paragraph: bool = True) -> bool:
    """True if lines[i] starts a new block (and so ends a paragraph or lazy continuation)."""
    line = lines[i]
    if (FENCE_RE.match(line) or ATX_RE.match(line) or QUOTE_RE.match(line)
            or HR_RE.match(line) or RAW_OPEN_RE.match(line) or HTML_INTERRUPT_RE.match(line)
            or is_table_start(lines, i)):
        return True
    m = LIST_RE.match(line)
    if m:
        if in_paragraph and not line[m.end():].strip():
            return False  # an empty list item cannot interrupt a paragraph
        marker = m.group(2)
        if in_paragraph and marker[0].isdigit():
            return int(marker[:-1]) == 1
        return True
    return False


def is_paragraph_line(line: str) -> bool:
    return bool(line.strip()) and indent(line) < 4 and not starts_block([line], 0, in_paragraph=False)


def fence_closes(opening: str, line: str) -> bool:
    if opening == "$$":
        return line.strip().startswith("$$")
    m = FENCE_RE.match(line)
    return bool(m) and m.group(1)[0] == opening[0] and len(m.group(1)) >= len(opening) \
        and not line.strip()[len(m.group(1)):].strip()


def mask(text: str) -> str:
    chars = list(text)
    for rx in MASK_RES:
        for m in rx.finditer(text):
            for k in range(m.start() + 1, m.end() - 1):
                chars[k] = "x"
    return "".join(chars)


def split_sentences(text: str) -> list[str]:
    return [text[s:e].strip() for s, e in sentences(mask(text)) if text[s:e].strip()]


def reflow_paragraph(para: list[str], mode: str) -> list[str]:
    # Split at hard line breaks. A backslash break stays in the text.
    segments: list[tuple[str, str]] = []
    cur: list[str] = []
    for k, line in enumerate(para):
        text = line.strip()
        last = k == len(para) - 1
        if not last and line.endswith("  "):
            cur.append(text)
            segments.append((" ".join(cur), "  "))
            cur = []
        elif not last and text.endswith("\\"):
            cur.append(text)
            segments.append((" ".join(cur), ""))
            cur = []
        else:
            cur.append(text)
    if cur:
        segments.append((" ".join(cur), ""))

    out: list[str] = []
    for text, hard_break in segments:
        lines = split_sentences(text) if mode == "sentence" else [text]
        lines = lines or [text]
        lines[-1] += hard_break
        out.extend(lines)
    return out


def unmark(line: str) -> str:
    return line[1:] if line.startswith(LIFTED) else line


def reflow(lines: list[str], mode: str, lift_fences: bool = True) -> list[str]:
    """Reflow markdown lines. Lines that must sit at column 0 come back marked with LIFTED."""
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]

        if not line.strip():
            out.append("")
            i += 1
            continue

        m = FENCE_RE.match(line)
        if m:
            opening = m.group(1)
            if lift_fences and opening[0] in "`~":
                k = indent(line)
                emit = lambda l: out.append(LIFTED + dedent(l, k))  # noqa: E731
            else:
                emit = out.append
            emit(line)
            i += 1
            if opening == "$$" and line.strip() != "$$" and line.strip().endswith("$$"):
                continue  # one-line math block
            while i < n:
                emit(lines[i])
                i += 1
                if fence_closes(opening, lines[i - 1]):
                    break
            continue

        if indent(line) >= 4:  # indented code block
            while i < n:
                if indent(lines[i]) >= 4 and lines[i].strip():
                    out.append(lines[i])
                    i += 1
                    continue
                j = i
                while j < n and not lines[j].strip():
                    j += 1
                if j > i and j < n and indent(lines[j]) >= 4:
                    out.extend(lines[i:j])
                    i = j
                    continue
                break
            continue

        if ATX_RE.match(line) or HR_RE.match(line) or LINKDEF_RE.match(line):
            out.append(line)
            i += 1
            continue

        raw = RAW_OPEN_RE.match(line)
        if raw or HTML_INTERRUPT_RE.match(line) or HTML_TAG_LINE_RE.match(line):
            end = f"</{raw.group(1).lower()}>" if raw else "-->" if line.lstrip().startswith("<!--") else None
            if end:
                while i < n:
                    out.append(lines[i])
                    i += 1
                    if end in lines[i - 1].lower():
                        break
            else:
                while i < n and lines[i].strip():
                    out.append(lines[i])
                    i += 1
            continue

        if is_table_start(lines, i):
            while i < n and lines[i].strip():
                out.append(lines[i])
                i += 1
            continue

        if QUOTE_RE.match(line):
            inner: list[str] = []
            while i < n:
                cur = lines[i]
                if QUOTE_RE.match(cur):
                    inner.append(QUOTE_RE.sub("", cur, count=1))
                elif cur.strip() and inner and is_paragraph_line(inner[-1]) \
                        and not starts_block(lines, i):
                    inner.append(cur.strip())  # lazy continuation
                else:
                    break
                i += 1
            # A lifted fence stays inside the quote, right after the marker.
            out.extend(">" + (" " + unmark(r) if r else "") for r in reflow(inner, mode, lift_fences))
            continue

        m = LIST_RE.match(line)
        if m:
            lead, marker, space = m.groups()
            # The output drops the 1-3 space lead before the marker. Content is
            # re-indented to the new column, so the structure stays the same.
            if not space or len(space) > 4:
                prefix = marker + " "
                first = line[len(lead) + len(marker) + 1:]
            else:
                prefix = marker + space
                first = line[len(lead) + len(prefix):]
            col = len(lead) + len(prefix)  # content column in the input
            item = [first] if first.strip() else []
            i += 1
            while i < n:
                cur = lines[i]
                if not cur.strip():
                    j = i
                    while j < n and not lines[j].strip():
                        j += 1
                    if item and j < n and indent(lines[j]) >= col:
                        item.extend([""] * (j - i))
                        i = j
                        continue
                    break
                if indent(cur) >= col:
                    item.append(dedent(cur, col))
                elif item and is_paragraph_line(item[-1]) \
                        and not starts_block(lines, i, in_paragraph=False):
                    item.append(cur.strip())  # lazy continuation (a sibling item ends it)
                else:
                    break
                i += 1
            body = reflow(item, mode, lift_fences)
            if not body or body[0].startswith(LIFTED):
                out.append(prefix.rstrip())
            else:
                out.append((prefix + body[0]).rstrip())
                body = body[1:]
            # A lifted fence ends the list. The rest of the item goes to column 0
            # with it, so that indented text after it does not turn into code.
            lifted = False
            for r in body:
                lifted = lifted or r.startswith(LIFTED)
                if not r:
                    out.append("")
                elif lifted:
                    out.append(r if r.startswith(LIFTED) else LIFTED + r)
                else:
                    out.append(" " * len(prefix) + r)
            # The lifted text is now a top-level paragraph. A following "2." could not
            # interrupt it and would read as paragraph text, so separate them.
            if lifted and out[-1] and i < n and lines[i].strip():
                out.append("")
            continue

        para = [line]
        i += 1
        setext = False
        while i < n:
            cur = lines[i]
            if not cur.strip():
                break
            if SETEXT_RE.match(cur):
                para.append(cur)
                i += 1
                setext = True
                break
            if starts_block(lines, i):
                break
            para.append(cur)
            i += 1
        out.extend(para if setext else reflow_paragraph(para, mode))
    return out


def reflow_text(text: str, mode: str = "sentence", lift_fences: bool = True) -> str:
    trailing = text.endswith("\n")
    lines = text.split("\n")
    if trailing:
        lines = lines[:-1]
    front: list[str] = []
    if lines and lines[0].strip() == "---":
        for j in range(1, len(lines)):
            if lines[j].strip() in ("---", "..."):
                front, lines = lines[:j + 1], lines[j + 1:]
                break
    body = [unmark(r) for r in reflow(lines, mode, lift_fences)]
    return "\n".join(front + body) + ("\n" if trailing else "")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Join hard-wrapped markdown lines and put each sentence on its own line.")
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--mode", choices=("sentence", "paragraph"), default="sentence",
                    help="one sentence per line (default) or one paragraph per line")
    ap.add_argument("--keep-fence-indent", action="store_true",
                    help="leave indented code fences where they are")
    out = ap.add_mutually_exclusive_group()
    out.add_argument("-i", "--in-place", action="store_true", help="rewrite the files")
    out.add_argument("--check", action="store_true", help="exit 1 if any file would change")
    out.add_argument("--diff", action="store_true", help="print a unified diff")
    args = ap.parse_args(argv)

    if len(args.files) > 1 and not (args.in_place or args.check or args.diff):
        ap.error("more than one file needs --in-place, --check or --diff")

    changed = []
    for path in args.files:
        try:
            old = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"{path}: {exc}", file=sys.stderr)
            return 2
        new = reflow_text(old, args.mode, lift_fences=not args.keep_fence_indent)
        if new != old:
            changed.append(path)
        if args.in_place:
            if new != old:
                path.write_text(new, encoding="utf-8")
        elif args.check:
            if new != old:
                print(f"would reflow: {path}")
        elif args.diff:
            sys.stdout.writelines(difflib.unified_diff(
                old.splitlines(keepends=True), new.splitlines(keepends=True),
                fromfile=f"{path}", tofile=f"{path} (reflowed)"))
        else:
            sys.stdout.write(new)

    if args.in_place:
        print(f"reflowed {len(changed)} of {len(args.files)} file(s).", file=sys.stderr)
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    sys.exit(main())
