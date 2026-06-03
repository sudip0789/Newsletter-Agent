from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.pdf_renderer import PdfRenderError, render_html_to_pdf


class TestPdfRenderer(unittest.TestCase):
    def test_render_html_to_pdf_raises_clear_error_when_playwright_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir_name:
            tmpdir = Path(tmpdir_name)
            html_path = tmpdir / "index.html"
            pdf_path = tmpdir / "newsletter.pdf"
            html_path.write_text("<html><body>Hello</body></html>", encoding="utf-8")

            with patch("src.pdf_renderer.sync_playwright", None):
                with self.assertRaises(PdfRenderError) as context:
                    render_html_to_pdf(html_path, pdf_path)

            self.assertIn("Playwright is not installed", str(context.exception))
            self.assertIn("python -m playwright install chromium", str(context.exception))

    def test_render_html_to_pdf_wraps_browser_runtime_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir_name:
            tmpdir = Path(tmpdir_name)
            html_path = tmpdir / "index.html"
            pdf_path = tmpdir / "newsletter.pdf"
            html_path.write_text("<html><body>Hello</body></html>", encoding="utf-8")

            class _FakeChromium:
                def launch(self) -> None:
                    raise RuntimeError("chromium missing")

            class _FakePlaywrightContext:
                def __enter__(self):
                    return type("FakePlaywright", (), {"chromium": _FakeChromium()})()

                def __exit__(self, exc_type, exc, tb) -> bool:
                    return False

            with patch("src.pdf_renderer.sync_playwright", return_value=_FakePlaywrightContext()):
                with self.assertRaises(PdfRenderError) as context:
                    render_html_to_pdf(html_path, pdf_path)

            self.assertIn("Chromium is unavailable", str(context.exception))
            self.assertIn("python -m playwright install chromium", str(context.exception))


if __name__ == "__main__":
    unittest.main()
