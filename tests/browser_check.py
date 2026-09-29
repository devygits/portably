"""Optional Chromium smoke + host-collision regression checks for Portably itself."""
from pathlib import Path
import re
import sys
import tempfile
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from check_browser import chromium_path
from project import create_project

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "screenshots"
OUT.mkdir(exist_ok=True)


def page_html(relative):
    page = ROOT / relative
    html = page.read_text()

    def css_file(path):
        raw = path.read_text()
        return re.sub(r'@import\s+url\(["\']([^"\']+)["\']\);', lambda m: css_file(path.parent / m.group(1)), raw)

    def inline(match):
        file = (page.parent / match.group(1)).resolve()
        if not file.is_relative_to(ROOT):
            raise ValueError("Unexpected stylesheet outside repository")
        return "<style>\n" + css_file(file) + "\n</style>"

    return re.sub(r'<link\s+rel="stylesheet"\s+href="([^"]+)"\s*/?>', inline, html)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, executable_path=chromium_path(), args=["--no-sandbox"])

    for width, height in ((1440, 900), (390, 844)):
        page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
        for name, relative in (("docs", "docs/index.html"), ("starter", "starter/index.html")):
            page.set_content(page_html(relative), wait_until="load")
            page.screenshot(path=str(OUT / f"{name}-{width}.png"), full_page=True)
            assert not page.evaluate("document.documentElement.scrollWidth > innerWidth + 1"), f"Horizontal overflow: {name} at {width}"
            assert page.locator("body.pbly").count() == 1
            assert page.evaluate("getComputedStyle(document.body).getPropertyValue('--pbly-space-5').trim()") == "1.25rem"
            if name == "starter":
                assert page.locator(".pbly-btn--primary").count() > 0
        page.close()

    page = browser.new_page()
    page.set_content(page_html("starter/index.html"), wait_until="load")

    result = page.evaluate("""() => {
      const outside = document.createElement('button');
      outside.className = 'pbly-btn pbly-btn--primary';
      outside.textContent = 'Outside';
      document.documentElement.appendChild(outside);
      const inside = document.querySelector('.pbly-btn--primary');
      const a = getComputedStyle(outside).backgroundColor;
      const b = getComputedStyle(inside).backgroundColor;
      outside.remove();
      return {outside: a, inside: b};
    }""")
    assert result["outside"] != result["inside"], result

    page.evaluate("document.body.classList.add('host-theme')")
    page.add_style_tag(content="""
      button { background: rgb(128, 128, 128); color: rgb(255, 0, 0); border-radius: 0; }
      .host-theme button { background: rgb(128, 128, 128); }
    """)
    host_test = page.evaluate("""() => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'pbly-btn pbly-btn--primary';
      button.textContent = 'Host collision test';
      document.querySelector('main').prepend(button);
      const buttonStyle = getComputedStyle(button);
      return {buttonBackground: buttonStyle.backgroundColor, buttonRadius: buttonStyle.borderRadius};
    }""")
    assert host_test["buttonBackground"] == "rgb(37, 99, 235)", host_test
    assert host_test["buttonRadius"] == "4px", host_test

    with tempfile.TemporaryDirectory() as tmp:
        custom = Path(tmp) / "acme"
        create_project(custom, "acme")
        generated = custom / "index.html"
        html = generated.read_text()

        def custom_css(path):
            raw = path.read_text()
            return re.sub(r'@import\s+url\(["\']([^"\']+)["\']\);', lambda m: custom_css(path.parent / m.group(1)), raw)

        def inline_custom(match):
            target = (generated.parent / match.group(1)).resolve()
            return "<style>\n" + custom_css(target) + "\n</style>"

        html = re.sub(r'<link\s+rel="stylesheet"\s+href="([^"]+)"\s*/?>', inline_custom, html)
        page.set_content(html, wait_until="load")
        assert page.locator("body.acme").count() == 1
        assert page.locator(".acme-btn--primary").count() > 0
        assert page.evaluate("getComputedStyle(document.body).getPropertyValue('--acme-space-5').trim()") == "1.25rem"
        assert "pbly-" not in generated.read_text()

    browser.close()
