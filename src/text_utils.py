from __future__ import annotations

import re
from html import escape
from typing import Any


UNESCAPED_DOLLAR_PATTERN = re.compile(r"(?<!\\)\$")


def escape_dollar_signs_for_markdown(value: Any) -> str:
    text = "" if value is None else str(value)
    return UNESCAPED_DOLLAR_PATTERN.sub(r"\\$", text)


def normalize_markdown_escaped_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace(r"\$", "$")


def to_safe_html_text(value: Any) -> str:
    normalized = normalize_markdown_escaped_text(value)
    return escape(normalized).replace("$", "&#36;")
