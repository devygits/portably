"""Checks for maintaining Portably itself (`portably check starter --framework`)."""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

from build_tokens import generate
from naming import default_namespace

ROOT = Path(__file__).resolve().parents[1]
SYSTEM_IMPORTS = ["layers.css", "reset.css", "button.css", "accessibility.css"]
PUBLIC_UNLAYERED = ("button.css", "accessibility.css")


class Stylesheets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag == "link" and "stylesheet" in (data.get("rel") or "").split():
            self.hrefs.append(data.get("href"))


def selector_headers(stylesheet):
    stylesheet = re.sub(r"/\*.*?\*/", "", stylesheet, flags=re.S)
    for found in re.finditer(r"([^{}]+)\{", stylesheet):
        text = found.group(1).strip()
        if text and not text.startswith("@"):
            yield text


def split_selector_group(group):
    parts, depth, start = [], 0, 0
    for pos, ch in enumerate(group):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(group[start:pos].strip())
            start = pos + 1
    parts.append(group[start:].strip())
    return parts


def foundation_problems(folder, namespace):
    """The canonical foundation's contract: scoped, layered where it should be, accessible."""
    css = {path.name: path.read_text(encoding="utf-8") for path in folder.glob("*.css")}
    if re.findall(r'@import\s+url\(["\']([^"\']+)["\']\)', css.get("system.css", "")) != SYSTEM_IMPORTS:
        yield "foundation/system.css", "Must import layers, reset, button and accessibility, in that order."
    if css.get("layers.css", "").strip() != f"@layer {namespace}-reset, {namespace}-tokens;":
        yield "foundation/layers.css", "Layer names don't match the namespace."
    if not css.get("reset.css", "").lstrip().startswith(f"@layer {namespace}-reset {{"):
        yield "foundation/reset.css", "The reset must live in the reset layer."
    for name in PUBLIC_UNLAYERED:
        if "@layer" in css.get(name, ""):
            yield f"foundation/{name}", "Public rules must stay unlayered."
    for name in ("reset.css",) + PUBLIC_UNLAYERED:
        for header in selector_headers(css.get(name, "")):
            for selector in split_selector_group(header):
                if not re.search(rf"(?<![\w-])\.{re.escape(namespace)}(?=[\s.:#\[,]|$)", selector):
                    yield f"foundation/{name}", f"Selector isn't scoped to .{namespace}: {selector}"
    joined = "\n".join(css.values())
    if "@media (max-width" in joined:
        yield "foundation/", "The foundation must not contain layout breakpoints."
    if ":root" in joined:
        yield "foundation/", "The foundation must not style :root."
    if ":focus-visible" not in css.get("reset.css", ""):
        yield "foundation/reset.css", "Must provide focus-visible styling."
    if "prefers-reduced-motion: reduce" not in css.get("reset.css", ""):
        yield "foundation/reset.css", "Must respect reduced-motion preferences."
    if f".{namespace} .{namespace}-btn:disabled" not in css.get("button.css", ""):
        yield "foundation/button.css", "Must style the native disabled state."
    if re.search(r"\b(?:STA|restaurant|Figma|Sugarcube)\b", joined, re.I):
        yield "foundation/", "Contains project- or research-specific names."


def framework_problems():
    namespace = default_namespace()
    yield from foundation_problems(ROOT / "foundation", namespace)

    for source in sorted((ROOT / "foundation").glob("*.css")):
        copy = ROOT / "starter" / "foundation" / source.name
        if not copy.is_file() or copy.read_text(encoding="utf-8") != source.read_text(encoding="utf-8"):
            yield f"starter/foundation/{source.name}", "Must be an exact copy of foundation/."

    page_dir = ROOT / "starter" / "pages"
    if page_dir.exists() and list(page_dir.rglob("*.html")):
        yield "starter/pages/", "The starter must not ship extra demonstration pages."

    tokens = json.loads((ROOT / "starter/tokens/tokens.json").read_text(encoding="utf-8"))
    if (ROOT / "starter/tokens/tokens.css").read_text(encoding="utf-8") != generate(tokens, namespace=namespace):
        yield "starter/tokens/tokens.css", "Out of date with tokens.json."

    parser = Stylesheets()
    parser.feed((ROOT / "docs" / "index.html").read_text(encoding="utf-8"))
    if parser.hrefs[:3] != ["foundation/system.css", "tokens/tokens.css", "css/project.css"]:
        yield "docs/index.html", "Must load its local foundation, generated tokens, then project CSS."
