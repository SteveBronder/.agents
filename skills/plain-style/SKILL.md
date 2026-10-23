---
name: plain-style
description: The user's style guide for prose in markdown documents (reports, memos, design docs, write-ups, READMEs, summaries), plus scripts that check its mechanical rules and reflow hard-wrapped markdown to one sentence per line. The guide keeps a calm, plain, researcher's register and removes the habits that make text read as machine-written, such as punchy closing clauses, lists of three, contrastive negation, and semicolons. Use this skill whenever you write, draft, rewrite, edit, proofread, or review prose in a markdown document, or when the user asks to make text plainer, less punchy, less like AI writing, to "apply the style guide", to "check the style", or to unwrap or reflow markdown lines, even if they do not name the guide. Skip it for code, code comments, commit messages, and agent instruction files such as CLAUDE.md or SKILL.md.
---

# Plain style

The guide in `references/style_guide.md` sets a calm, factual register for documents.
Most of its rules target habits of LLM prose.
Readers notice those habits quickly and trust the document less.
You are an LLM, so these habits are your defaults.
Expect to find them in your own drafts.

## Workflow

1. **Read the full guide** at `~/.claude/skills/plain-style/references/style_guide.md` before writing or revising.
   It is about 220 lines.
   Read the before-and-after examples too, because they show where each rule's boundary sits in a way the rule statements alone do not.

2. **Write or revise the document.**
   When revising someone else's text, change the register and keep the substance.
   Leave the meaning, technical content, numbers, and official names as they are.
   Rule 8 applies here.
   Plain sentences that are already fine should stay as they are.
   Do not hard-wrap lines.

3. **Reflow the file** so that each sentence starts on a new line:

```bash
python3 ~/.claude/skills/plain-style/scripts/reflow_md.py --in-place path/to/doc.md
```

Prose hard-wrapped at about 80 columns is a strong sign of machine-written markdown.
The script joins the lines inside each paragraph, list item, and blockquote, then starts each sentence on its own line.
Markdown renders the joined text the same as before.
One sentence per line also makes diffs easier to review, and each checker line number then points at a single sentence.
Indented code fences move to column 0, because many viewers only highlight a fence that starts the line.
A fence inside a list item ends the list, so the rest of that item moves to column 0 with it.
Other code blocks, math blocks, tables, headings, HTML, and front matter are left alone.

Flags:
- `--mode paragraph` puts each paragraph on one line instead.
- `--check` exits with status 1 if the file would change, and `--diff` prints the change.
  Neither one edits the file.
- `--keep-fence-indent` leaves indented code fences where they are.
- Without `--in-place`, `--check`, or `--diff`, the script prints the result to stdout.

4. **Run the checker** on the file:

```bash
python3 ~/.claude/skills/plain-style/scripts/check_style.py path/to/doc.md
```

Each finding prints as `file:line: severity [rule, guide section] message | snippet`.
The script exits with status 1 while errors remain.
Fix every error.
A warning marks a pattern the guide says to watch for.
Reread that sentence and change it if it breaks the rule.
Leave it if it is plain and needed.

Flags:
- `--skip-quoted` ignores text in double quotes and in blockquotes.
  Use it when the document quotes other people's words or contains before-and-after examples, since quotations should not be rewritten.
- `--max-words N` changes the sentence-length limit (default 40).
- `--ignore RULE` skips one rule and can be repeated.
- `--json` prints the findings as JSON.
- `--list-rules` shows what the script checks.

5. **Reread the whole document for the rules the checker cannot see.**
   The script only covers patterns a regex can find reliably.
   The list below covers the rest.

6. **Reflow and run the checker again** after the reread, because fixes can introduce new problems.
   Splitting a long sentence, for example, can leave a fragment that starts with "so that".

## Fixing flags without dodging them

The checker matches surface patterns.
A fix that only changes the surface usually breaks a different rule.

- **Semicolon.**
  Split it into two sentences or join the clauses with a conjunction.
  Swapping in a colon produces the "X: Y" sentence of Rule 1.
  A dash does the same job as the semicolon and has the same problem.
- **Long sentence.**
  Split it at a clause boundary.
  Each piece should still read as a full sentence.
- **"for every".**
  Say it plainly, as in "with sources and notes" or "the price of each task is fixed".
- **"and its" / "with its".**
  Rebuild the phrase ("model, with documentation").
  Replacing "its" with "the" keeps the same shape.
- **Jargon and figurative verbs.**
  Use the ordinary word the guide gives ("is part of", "schedule", "accompanies") or a plain verb such as "leads to" or "is used in".
- **Non-ASCII.**
  Use the replacement the checker suggests.
  For an em dash, rewrite the sentence.
  Typing "--" in its place keeps the same construction.

## Rules to check by reading

These are the most common problems in LLM drafts, and the script does not catch them.
Look for them on purpose.
Check every colon, every list, every "not", and every sentence that ends in ", and ..." or ", so ...".

- **Rule 1.**
  A colon inside a sentence that sets up a payoff ("X: Y").
- **Rule 2.**
  A question framing used in place of a noun ("what happens when" for "the effects of").
- **Rule 3.**
  Lists of three, unless every item must be named.
  Do not split them into "X and Y. Also Z."
- **Rule 6.**
  A tacked-on ", clipped-participle" flourish ("French cooking, demystified").
- **Rule 11.**
  Contrastive negation ("an X, not a Y", "not just X but Y").
- **Rule 15.**
  A clause hung off a noun that points back with "it" or "them".
- **Rule 17.**
  "No" in front of a noun as the negation ("requires no site visits").
  Negate the verb.
- **Rule 18.**
  A ", and" or ", so" second half that lands like a payoff.

These need judgment about content:

- **Rules 4, 5, 7.**
  Candor as a sales move, people's verbs given to things, and explaining why the design is clever.
- **Rules 8 and 16.**
  Leave plain sentences unpolished and vary sentence shapes.
- **Rules 9, 10, 13, 14.**
  Cut specialist detail the reader does not need, explain central methods in a sentence, use the field's working vocabulary, and qualify empirical expectations.
- **Rule 12.**
  Introduce lists of contents with "such as" or "items like the following".
- **Voice, Claims, Structure, Commitments.**
  Present tense for facts, headings that match their content, reference material inside the section that uses it, and a final pass over the whole document's structure.

## Reviewing instead of rewriting

If the user asks for a review, report each problem with its line number, the rule, and a suggested rewrite.
Leave the file unedited unless they ask for changes, which includes the reflow.
Use `reflow_md.py --check` to report whether the file needs reflowing.
Include the checker's summary line so they can see where the document stands.
