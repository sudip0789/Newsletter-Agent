import unittest

from src.text_utils import (
    escape_dollar_signs_for_markdown,
    normalize_markdown_escaped_text,
    to_safe_html_text,
)


class TestTextUtils(unittest.TestCase):
    def test_escape_dollar_signs_for_markdown_escapes_currency(self) -> None:
        value = "$97 billion on infrastructure to win $37 billion"

        self.assertEqual(
            escape_dollar_signs_for_markdown(value),
            r"\$97 billion on infrastructure to win \$37 billion",
        )

    def test_escape_dollar_signs_for_markdown_does_not_double_escape(self) -> None:
        value = r"\$97 billion already escaped"

        self.assertEqual(
            escape_dollar_signs_for_markdown(value),
            r"\$97 billion already escaped",
        )

    def test_normalize_markdown_escaped_text_restores_currency(self) -> None:
        value = r"\$97 billion on infrastructure to win \$37 billion"

        self.assertEqual(
            normalize_markdown_escaped_text(value),
            "$97 billion on infrastructure to win $37 billion",
        )

    def test_to_safe_html_text_preserves_currency_as_literal_html(self) -> None:
        value = "$97 billion & growing"

        self.assertEqual(
            to_safe_html_text(value),
            "&#36;97 billion &amp; growing",
        )


if __name__ == "__main__":
    unittest.main()
