"""Tests for check_style.py. Run with: python3 -m unittest test_check_style (from scripts/)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_style import check_text, sentences  # noqa: E402


def run(md: str, **kwargs):
    return check_text("doc.md", md.splitlines(), **kwargs)


def rules(md: str, **kwargs):
    return [(f.rule, f.line) for f in run(md, **kwargs)]


class TestPhraseRules(unittest.TestCase):
    def test_semicolon(self):
        self.assertEqual(rules("One clause; another clause."), [("semicolon", 1)])

    def test_semicolon_in_heading_and_table(self):
        md = "# Title; subtitle\n\n| a | b; c |\n|---|---|\n| d | e |"
        self.assertEqual(rules(md), [("semicolon", 1), ("semicolon", 3)])

    def test_for_every(self):
        self.assertEqual(rules("We keep a record for every change."), [("for-every", 1)])

    def test_jargon(self):
        md = "VR sits inside DETR.\n\nThe meeting cadence is weekly.\n\nA sidecar rides along."
        self.assertEqual(rules(md), [("jargon", 1), ("jargon", 3), ("jargon", 5)])

    def test_figurative_verb(self):
        self.assertEqual(rules("The uncertainty carries through to the results."),
                         [("figurative-verb", 1)])

    def test_and_its(self):
        self.assertEqual(rules("The model and its documentation."), [("and-its", 1)])

    def test_candor(self):
        self.assertEqual(rules("Frankly, the data are thin."), [("candor", 1)])
        self.assertEqual(rules("To be clear, we did not test it."), [("candor", 1)])

    def test_pitch_connective(self):
        self.assertEqual(rules("We run it first so that the model is ready."),
                         [("pitch-connective", 1)])

    def test_orientation(self):
        self.assertEqual(rules("This section describes the method."), [("orientation", 1)])
        self.assertEqual(rules("Sections 2.1 to 2.4 describe the tasks."), [("orientation", 1)])

    def test_callout_and_icon(self):
        md = "> [!NOTE]\n> Something here.\n\nDone \u2705 today."
        self.assertEqual(rules(md), [("callout", 1), ("non-ascii", 4)])

    def test_clean_text_has_no_findings(self):
        md = "The model uses survey data. It runs each scenario once.\n"
        self.assertEqual(rules(md), [])


class TestNonAscii(unittest.TestCase):
    def msgs(self, md):
        return [(f.line, f.message) for f in run(md) if f.rule == "non-ascii"]

    def test_em_dash(self):
        [(line, msg)] = self.msgs("One clause \u2014 another.")
        self.assertEqual(line, 1)
        self.assertIn("U+2014 EM DASH", msg)
        self.assertIn("Rewrite with a comma", msg)

    def test_curly_quotes_counted_once_per_line(self):
        found = self.msgs("He said \u201chi\u201d and \u201cbye\u201d.")
        self.assertEqual(len(found), 2)
        self.assertIn("(2 on this line)", found[0][1])
        self.assertIn('Use ".', found[0][1])

    def test_accented_letter_suggests_base(self):
        [(_, msg)] = self.msgs("A r\u00e9sum\u00e9 is attached.")
        self.assertIn('Use "e".', msg)

    def test_invisible_and_space_characters(self):
        found = dict(self.msgs("\ufeffStart.\n\nA\u00a0b.\n\nC\u200bd."))
        self.assertIn("Delete it", found[1])
        self.assertIn("plain space", found[3])
        self.assertIn("Delete it", found[5])

    def test_checked_in_code_and_front_matter(self):
        md = "---\ntitle: caf\u00e9\n---\n```\nx = \"\u2192\"\n```\nText."
        self.assertEqual([line for line, _ in self.msgs(md)], [2, 5])

    def test_checked_even_with_skip_quoted(self):
        self.assertEqual(rules('He wrote "caf\u00e9".', skip_quoted=True), [("non-ascii", 1)])

    def test_ascii_text_is_clean(self):
        self.assertEqual(self.msgs("Plain text -- with 'quotes' and \"more\"... -> done."), [])


class TestSentenceLength(unittest.TestCase):
    def test_long_sentence_flagged(self):
        words = " ".join(["word"] * 41) + "."
        self.assertEqual(rules(words), [("sentence-length", 1)])

    def test_limit_is_inclusive(self):
        words = " ".join(["word"] * 40) + "."
        self.assertEqual(rules(words), [])

    def test_max_words_flag(self):
        self.assertEqual(rules("One two three four five six.", max_words=5),
                         [("sentence-length", 1)])

    def test_line_number_of_sentence_in_wrapped_paragraph(self):
        long = " ".join(["word"] * 41) + "."
        md = "Short first sentence.\nStill the same paragraph. " + long
        self.assertEqual(rules(md), [("sentence-length", 2)])

    def test_abbreviations_do_not_split(self):
        spans = list(sentences("Use a source, e.g. the ACS. Then stop."))
        self.assertEqual(len(spans), 2)

    def test_decimal_does_not_split(self):
        spans = list(sentences("See Section 2.2 for details. Then stop."))
        self.assertEqual(len(spans), 2)

    def test_list_items_are_separate(self):
        item = " ".join(["word"] * 25)
        md = f"- {item}\n- {item}"
        self.assertEqual(rules(md), [])

    def test_headings_and_tables_not_length_checked(self):
        long = " ".join(["word"] * 50)
        self.assertEqual(rules(f"# {long}\n\n| {long} |"), [])


class TestMarkdownHandling(unittest.TestCase):
    def test_fenced_code_skipped(self):
        md = "```python\nx = 1; y = 2\n```\nPlain text."
        self.assertEqual(rules(md), [])

    def test_inline_code_skipped(self):
        self.assertEqual(rules("Run `a; b` in the shell."), [])

    def test_html_entities_and_links_skipped(self):
        md = "Tom &amp; Jerry. See [the docs](https://x.org/a;b)."
        self.assertEqual(rules(md), [])

    def test_html_comment_skipped(self):
        md = "<!-- a; b\nc; d -->\nText."
        self.assertEqual(rules(md), [])

    def test_front_matter_skipped(self):
        md = "---\ntitle: a; b\n---\nText."
        self.assertEqual(rules(md), [])

    def test_quotes_checked_by_default(self):
        self.assertEqual(rules('He wrote "a; b" once.'), [("semicolon", 1)])

    def test_skip_quoted(self):
        md = 'He wrote "a; b" once.\n\n> c; d'
        self.assertEqual(rules(md, skip_quoted=True), [])

    def test_ignore(self):
        self.assertEqual(rules("a; b", ignore={"semicolon"}), [])


if __name__ == "__main__":
    unittest.main()
