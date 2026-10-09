"""Render tools/icon.svg to the brand PNGs with Chromium (via Playwright).

Usage: python tools/render_icon.py  (needs `pip install playwright` and a Chromium;
set CHROMIUM_PATH to use an already installed one)
"""

import os
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SVG = (ROOT / "tools" / "icon.svg").read_text()
OUT = ROOT / "custom_components" / "task_reminder" / "brand"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        for size, suffix in ((256, ""), (512, "@2x")):
            page = browser.new_page(viewport={"width": size, "height": size})
            page.set_content(
                f"<style>html,body{{margin:0;background:transparent}}"
                f"svg{{width:{size}px;height:{size}px;display:block}}</style>{SVG}"
            )
            for name in ("icon", "logo"):
                page.screenshot(path=str(OUT / f"{name}{suffix}.png"), omit_background=True)
        browser.close()


if __name__ == "__main__":
    main()
