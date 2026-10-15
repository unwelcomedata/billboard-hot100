"""Render the infographic SVGs to PNG at exact pixel size (Playwright/Chromium).

Usage: .venv/bin/python scripts/_render_infographic.py

Pattern copied from abortion-cause-of-death/scripts/_render_infographic.py
(cairosvg isn't installed and the venvs are Py3.14). The billboard .venv already
carries Playwright, so no cross-project venv is needed.
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJECT = Path(__file__).resolve().parents[1]
DOCS = PROJECT / "docs"

JOBS = [
    ("infographic_billboard.svg", "infographic_billboard.png", 1200, 2240),
    ("infographic_billboard_social.svg", "infographic_billboard_social.png", 1600, 900),
]


def main() -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for svg_name, png_name, w, h in JOBS:
            svg = (DOCS / svg_name).read_text(encoding="utf-8")
            html = (
                "<!doctype html><html><head><style>*{margin:0;padding:0}</style>"
                f"</head><body>{svg}</body></html>"
            )
            page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            page.set_content(html)
            page.wait_for_timeout(300)
            page.screenshot(path=str(DOCS / png_name), clip={"x": 0, "y": 0, "width": w, "height": h})
            page.close()
            print(f"rendered {png_name} ({w}x{h})")
        browser.close()


if __name__ == "__main__":
    main()
