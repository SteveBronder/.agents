"""Tests for reflow_md.py. Run with: python3 -m unittest test_reflow_md (from scripts/)."""
import sys
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from reflow_md import reflow_text  # noqa: E402

WRAPPED = """\
You produce a summary the
user can read in a few minutes and act on. It covers the PR's claims, whether the
evidence holds up, and the questions to ask the author. The review is
**investigative**. Each finding should rest on something you checked, such as a line
of code, a computed value, or a traced test input. A general impression is not
enough.
"""


def md(s: str) -> str:
    return textwrap.dedent(s).lstrip("\n")


class TestParagraphs(unittest.TestCase):
    def test_paragraph_mode_joins_lines(self):
        self.assertEqual(reflow_text(WRAPPED, "paragraph"), (
            "You produce a summary the user can read in a few minutes and act on. "
            "It covers the PR's claims, whether the evidence holds up, and the questions to ask the author. "
            "The review is **investigative**. "
            "Each finding should rest on something you checked, such as a line of code, "
            "a computed value, or a traced test input. A general impression is not enough.\n"))

    def test_sentence_mode_one_sentence_per_line(self):
        self.assertEqual(reflow_text(WRAPPED), (
            "You produce a summary the user can read in a few minutes and act on.\n"
            "It covers the PR's claims, whether the evidence holds up, and the questions to ask the author.\n"
            "The review is **investigative**.\n"
            "Each finding should rest on something you checked, such as a line of code, "
            "a computed value, or a traced test input.\n"
            "A general impression is not enough.\n"))

    def test_paragraphs_stay_separate(self):
        self.assertEqual(reflow_text("One\ntwo.\n\nThree\nfour.\n"), "One two.\n\nThree four.\n")

    def test_abbreviation_and_decimal_do_not_split(self):
        self.assertEqual(reflow_text("Use a source, e.g. the ACS in Section 2.2. Then stop.\n"),
                         "Use a source, e.g. the ACS in Section 2.2.\nThen stop.\n")

    def test_inline_code_link_and_url_not_split(self):
        text = "Run `a. B` now. See [the docs](https://x.org/a. B) and https://x.org/v1.2. Done.\n"
        self.assertEqual(reflow_text(text),
                         "Run `a. B` now.\nSee [the docs](https://x.org/a. B) and https://x.org/v1.2.\nDone.\n")

    def test_quoted_sentence_inside_sentence(self):
        text = '"The data tell us." became "The data show." in the draft.\n'
        self.assertEqual(reflow_text(text), text)

    def test_hard_breaks_kept(self):
        self.assertEqual(reflow_text("Line one  \nline two.\nmore.\n"), "Line one  \nline two. more.\n")
        self.assertEqual(reflow_text("Line one\\\nline two.\n"), "Line one\\\nline two.\n")

    def test_setext_heading_kept(self):
        text = "A title\n=======\n\nBody\ntext.\n"
        self.assertEqual(reflow_text(text), "A title\n=======\n\nBody text.\n")

    def test_number_mid_paragraph_is_not_a_list(self):
        self.assertEqual(reflow_text("It started in\n1990. Then it grew.\n"),
                         "It started in 1990.\nThen it grew.\n")

    def test_autolink_line_is_paragraph_text(self):
        text = "- A paper. PLDI 1991.\n  <https://x.org/a>\n  (PDF: <https://x.org/b>).\n"
        self.assertEqual(reflow_text(text),
                         "- A paper.\n  PLDI 1991. <https://x.org/a> (PDF: <https://x.org/b>).\n")

    def test_inline_html_paragraph_is_reflowed(self):
        self.assertEqual(reflow_text("<em>Note</em> that\nthis wraps.\n"), "<em>Note</em> that this wraps.\n")

    def test_lone_tag_line_is_kept(self):
        text = "<img src=\"a.png\">\nnext\nline\n"
        self.assertEqual(reflow_text(text), text)

    def test_bullet_interrupts_paragraph(self):
        self.assertEqual(reflow_text("Items:\n- one\n- two\n"), "Items:\n- one\n- two\n")


class TestLists(unittest.TestCase):
    def test_wrapped_bullet(self):
        text = md("""
            - First item is
              wrapped here. Second sentence.
            - Next item.
            """)
        self.assertEqual(reflow_text(text), md("""
            - First item is wrapped here.
              Second sentence.
            - Next item.
            """))

    def test_paragraph_mode_bullet(self):
        text = "- First item is\n  wrapped here. Second sentence.\n"
        self.assertEqual(reflow_text(text, "paragraph"),
                         "- First item is wrapped here. Second sentence.\n")

    def test_ordered_list_and_lazy_continuation(self):
        text = "1. First item\nlazy line. Next.\n2. Second item.\n"
        self.assertEqual(reflow_text(text), "1. First item lazy line.\n   Next.\n2. Second item.\n")

    def test_nested_list(self):
        text = md("""
            - Outer item
              wrapped.
              - Inner item
                wrapped. Two.
            - Back out.
            """)
        self.assertEqual(reflow_text(text), md("""
            - Outer item wrapped.
              - Inner item wrapped.
                Two.
            - Back out.
            """))

    def test_loose_list_with_second_paragraph(self):
        text = "- Item one\n  wraps.\n\n  Second para\n  wraps.\n\n- Item two.\n"
        self.assertEqual(reflow_text(text), "- Item one wraps.\n\n  Second para wraps.\n\n- Item two.\n")

    def test_code_block_inside_item_kept_with_flag(self):
        text = "- Item:\n\n  ```\n  a = 1\n  b = 2\n  ```\n"
        self.assertEqual(reflow_text(text, lift_fences=False), text)

    def test_leftover_list_indent_removed(self):
        self.assertEqual(reflow_text("   Flags:\n   - a\n     wraps.\n   - b\n"), "Flags:\n- a wraps.\n- b\n")
        self.assertEqual(reflow_text(" 1. a\n    - nested\n"), "1. a\n   - nested\n")

    def test_task_list(self):
        self.assertEqual(reflow_text("- [ ] Do\n  this. Then that.\n"), "- [ ] Do this.\n  Then that.\n")


class TestQuotes(unittest.TestCase):
    def test_wrapped_quote(self):
        self.assertEqual(reflow_text("> One sentence\n> wraps. Two.\n"), "> One sentence wraps.\n> Two.\n")

    def test_lazy_quote_line(self):
        self.assertEqual(reflow_text("> One sentence\nwraps.\n"), "> One sentence wraps.\n")

    def test_nested_quote(self):
        self.assertEqual(reflow_text("> > Deep\n> > text.\n"), "> > Deep text.\n")

    def test_list_inside_quote(self):
        self.assertEqual(reflow_text("> - Item\n>   wraps.\n"), "> - Item wraps.\n")

    def test_blank_line_inside_quote(self):
        self.assertEqual(reflow_text("> A\n> b.\n>\n> C.\n"), "> A b.\n>\n> C.\n")


class TestFenceLifting(unittest.TestCase):
    def test_top_level_indented_fence(self):
        text = "Run:\n\n   ```bash\n   python3 x.py\n     indented\n   ```\n"
        self.assertEqual(reflow_text(text), "Run:\n\n```bash\npython3 x.py\n  indented\n```\n")

    def test_fence_in_list_item_lifts_rest_of_item(self):
        text = md("""
            3. **Reflow the file** so
               lines join:

               ```bash
               python3 reflow_md.py --in-place doc.md
               ```

               The script joins
               lines. It keeps code.

               Flags:
               - `--mode paragraph` puts each
                 paragraph on one line.

            4. **Run the checker** on the file.
            """)
        self.assertEqual(reflow_text(text), md("""
            3. **Reflow the file** so lines join:

            ```bash
            python3 reflow_md.py --in-place doc.md
            ```

            The script joins lines.
            It keeps code.

            Flags:
            - `--mode paragraph` puts each paragraph on one line.

            4. **Run the checker** on the file.
            """))

    def test_nested_item_lift_also_lifts_parent_remainder(self):
        text = md("""
            - Outer:
              - Inner:

                ```
                code
                ```

                Inner tail.

              Outer tail.
            - Next.
            """)
        self.assertEqual(reflow_text(text), md("""
            - Outer:
              - Inner:

            ```
            code
            ```

            Inner tail.

            Outer tail.

            - Next.
            """))

    def test_blank_line_before_next_item_after_lift(self):
        text = "1. Step:\n   ```\n   x\n   ```\n   More.\n2. Next.\n"
        self.assertEqual(reflow_text(text), "1. Step:\n```\nx\n```\nMore.\n\n2. Next.\n")

    def test_item_starting_with_fence(self):
        self.assertEqual(reflow_text("- ```\n  x\n  ```\n"), "-\n```\nx\n```\n")

    def test_fence_in_quote_stays_in_quote(self):
        self.assertEqual(reflow_text(">    ```bash\n>    x\n>    ```\n"), "> ```bash\n> x\n> ```\n")
        self.assertEqual(reflow_text("> - Item:\n>\n>   ```\n>   x\n>   ```\n"),
                         "> - Item:\n>\n> ```\n> x\n> ```\n")

    def test_tilde_fence_lifted_and_math_not(self):
        self.assertEqual(reflow_text("  ~~~\n  x\n  ~~~\n"), "~~~\nx\n~~~\n")
        text = "- Item:\n\n  $$\n  x\n  $$\n"
        self.assertEqual(reflow_text(text), text)

    def test_tabs_in_top_level_code_kept(self):
        text = "```make\nall:\n\tcc main.c\n```\n"
        self.assertEqual(reflow_text(text), text)


class TestUntouched(unittest.TestCase):
    def check_same(self, text):
        self.assertEqual(reflow_text(text), text)
        self.assertEqual(reflow_text(text, "paragraph"), text)

    def test_fenced_code(self):
        self.check_same("```python\nx = 1. Y = 2\nlong\nline\n```\n")

    def test_tilde_fence_and_math(self):
        self.check_same("~~~\na\nb\n~~~\n\n$$\nx = 1.\ny\n$$\n")

    def test_indented_code(self):
        self.check_same("Para.\n\n    code line\n    more code\n\n    after blank\n\nPara.\n")

    def test_table(self):
        self.check_same("| a | b |\n|---|---|\n| one. Two | x |\n")
        self.check_same("a | b\n--|--\n1 | 2\n")

    def test_headings_rules_and_link_defs(self):
        self.check_same("# Title. With dot\n\n---\n\n[ref]: https://x.org/a.b\n")

    def test_html_and_comments(self):
        self.check_same("<div>\nSome. Text\nhere\n</div>\n\n<!-- a\nb. C\n-->\n")

    def test_tab_indented_code(self):
        self.check_same("Usage:\n\n\t--title TEXT  # title\n\t--width NUM  # width\n")

    def test_pre_block_with_blank_lines(self):
        self.check_same("<pre>\nkeep\n\nthis. Text\n</pre>\n")

    def test_front_matter(self):
        self.check_same("---\ntitle: A. B\ntags: x\n---\n")

    def test_no_trailing_newline(self):
        self.assertEqual(reflow_text("A\nb."), "A b.")


class TestIdempotent(unittest.TestCase):
    def test_reflow_twice_is_stable(self):
        doc = WRAPPED + "\n" + md("""
            # Heading

            - Item one
              wraps. Two.
              1. Nested
                 ordered. Item.

            > Quote
            > wraps. Again.

            1. Step with code:

               ```bash
               run it
               ```

               After the
               code. More.
            2. Next step.

            ```
            code. Stays
            ```
            """)
        for mode in ("sentence", "paragraph"):
            once = reflow_text(doc, mode)
            self.assertEqual(reflow_text(once, mode), once, mode)


if __name__ == "__main__":
    unittest.main()
