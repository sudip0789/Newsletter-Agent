from __future__ import annotations

from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


class PdfRenderError(RuntimeError):
    """Raised when the newsletter PDF cannot be rendered."""


def render_html_to_pdf(html_path: Path, pdf_path: Path) -> None:
    html_file = Path(html_path).resolve()
    output_file = Path(pdf_path).resolve()

    if sync_playwright is None:
        raise PdfRenderError(
            "Playwright is not installed. Add `playwright` to the environment and run "
            "`python -m playwright install chromium` before building the site."
        )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    if output_file.exists():
        output_file.unlink()

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(
                viewport={"width": 1200, "height": 1600},
                device_scale_factor=2,
            )
            page.goto(html_file.as_uri(), wait_until="networkidle")
            page.emulate_media(media="print")
            page.pdf(
                path=str(output_file),
                print_background=True,
                prefer_css_page_size=True,
                format="Letter",
            )
            browser.close()
    except Exception as exc:
        raise PdfRenderError(
            "Chromium is unavailable for PDF rendering. Run "
            "`python -m playwright install chromium` and try again."
        ) from exc
