"""Lightweight static handoff checks for a Portably client project."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from check_system import html_pages
from project import HANDOFF_FILES

REMOTE = re.compile(r"^(?:https?:)?//", re.I)
# <link rel> values that make the browser download the file.
LOADED_RELS = {"stylesheet", "icon", "apple-touch-icon", "preload", "modulepreload", "manifest", "mask-icon"}
SKIP_SCHEMES = ("mailto:", "tel:", "data:", "javascript:")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.refs = []
        self.inline_styles = []
        self.role_buttons = []
        self.images_without_alt = []
        self.open = []
        self.page_sections = []
        self.app_shell = False

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        classes = (data.get("class") or "").split()
        if "app-shell" in classes:
            self.app_shell = True
        if "wrapper" in classes:
            for _, section in reversed(self.open):
                if section is not None:
                    section["wrapper"] = True
                    break
        if tag not in VOID:
            section = None
            if tag == "section" and self.open and self.open[-1][0] == "main":
                section = {"line": self.getpos()[0], "classes": classes, "wrapper": False}
                self.page_sections.append(section)
            self.open.append((tag, section))
        line = self.getpos()[0]
        if data.get("id"):
            self.ids.add(data["id"])
        if "style" in data:
            self.inline_styles.append(line)
        if data.get("role") == "button" and tag != "button":
            self.role_buttons.append((line, tag))
        if tag == "img" and "alt" not in data:
            self.images_without_alt.append((line, data.get("src", "<unknown>")))

        if tag == "a" and data.get("href") is not None:
            self.refs.append(("link", data["href"], line))
        if tag == "link" and data.get("href"):
            loaded = set((data.get("rel") or "").lower().split()) & LOADED_RELS
            self.refs.append(("resource" if loaded else "reference", data["href"], line))
        for attr in ("src", "poster"):
            if data.get(attr):
                self.refs.append(("resource", data[attr], line))

        srcset = data.get("srcset")
        if srcset:
            for candidate in srcset.split(","):
                value = candidate.strip().split()[0]
                if value:
                    self.refs.append(("resource", value, line))


    def handle_endtag(self, tag):
        for index in range(len(self.open) - 1, -1, -1):
            if self.open[index][0] == tag:
                del self.open[index:]
                break

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)


def anatomy_issues(rel, parsed):
    if parsed.app_shell:
        return
    for section in parsed.page_sections:
        where = f"{rel}:{section['line']}"
        if "section" not in section["classes"]:
            yield "anatomy", where, "This <section> in <main> has no `section` class."
        if not section["wrapper"]:
            yield "anatomy", where, "This section has no `wrapper` inside; put its content in <div class=\"wrapper\">."


def parse_page(path):
    parser = Page()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


def is_remote(value):
    return bool(REMOTE.match(value))


def resolve_local(base, raw):
    parsed = urlsplit(raw)
    path = unquote(parsed.path)
    if not path:
        return base, parsed.fragment
    if path.startswith("/"):
        return None, parsed.fragment
    return (base.parent / path).resolve(), parsed.fragment


def image_signature_ok(path):
    suffix = path.suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        return True
    data = path.read_bytes()[:16]
    if suffix == ".png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix in {".jpg", ".jpeg"}:
        return data.startswith(b"\xff\xd8\xff")
    if suffix == ".gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    if suffix == ".webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return True


def css_urls(text):
    for value in re.findall(r"url\(\s*['\"]?([^)'\"\s]+)", text, flags=re.I):
        yield value
    for value in re.findall(r"@import\s+(?:url\()?['\"]([^'\"]+)", text, flags=re.I):
        yield value


def inspect_project(project):
    """Return (group, where, detail) for every handoff problem in the project's pages, CSS and assets."""
    project = Path(project).resolve()
    issues = []

    def add(group, where, detail):
        issues.append((group, str(where), detail))

    for name in HANDOFF_FILES:
        if not (project / name).is_file():
            add("handoff-file", name, f"The project has no {name}.")

    pages = html_pages(project)
    page_cache = {page: parse_page(page) for page in pages}

    for page, parsed in page_cache.items():
        rel = page.relative_to(project).as_posix()
        for line, src in parsed.images_without_alt:
            add("missing-alt", f"{rel}:{line}", f"<img src=\"{src}\"> has no alt text.")
        for line in parsed.inline_styles:
            add("inline-style", f"{rel}:{line}", "This element has a style attribute.")
        for line, tag in parsed.role_buttons:
            add("fake-button", f"{rel}:{line}", f"A <{tag}> acts as a button (role=\"button\").")
        issues.extend(anatomy_issues(rel, parsed))

        for kind, raw, line in parsed.refs:
            where = f"{rel}:{line}"
            value = raw.strip()
            if not value or value.startswith(SKIP_SCHEMES):
                continue
            if is_remote(value):
                if kind == "resource":  # links people click (and rel=canonical and the like) aren't dependencies
                    add("remote", where, f"Loads {value}")
                continue
            if kind == "reference":
                continue

            target, fragment = resolve_local(page, value)
            if target is None:
                add("host-root", where, f"`{value}` starts with / and can't be checked here.")
                continue

            if kind == "link":
                if value == "#" or (not urlsplit(value).path and not fragment):
                    add("broken-link", where, f"A link points at `{value}`, a placeholder that goes nowhere.")
                    continue
                if urlsplit(value).path and not target.exists():
                    add("broken-link", where, f"A link points at `{value}`, which doesn't exist.")
                    continue
                if fragment:
                    fragment_page = target if target.suffix.lower() == ".html" else page if not urlsplit(value).path else target
                    if fragment_page.is_file() and fragment_page.suffix.lower() == ".html":
                        parsed_target = page_cache.get(fragment_page) or parse_page(fragment_page)
                        if fragment not in parsed_target.ids:
                            label = fragment_page.relative_to(project).as_posix() if fragment_page.is_relative_to(project) else fragment_page
                            add("broken-link", where, f"A link points at #{fragment}, but {label} has no element with that id.")
                continue

            if not target.exists():
                add("missing-file", where, f"`{value}` doesn't exist.")

    for css in sorted(list((project / "css").rglob("*.css")) + list((project / "foundation").rglob("*.css"))):
        rel = css.relative_to(project).as_posix()
        for raw in css_urls(css.read_text(encoding="utf-8")):
            value = raw.strip()
            if not value or value.startswith(SKIP_SCHEMES) or value.startswith("#") or value.startswith("var("):
                continue
            if is_remote(value):
                add("remote", rel, f"Loads {value}")
                continue
            parsed = urlsplit(value)
            if parsed.path.startswith("/"):
                add("host-root", rel, f"`{value}` starts with / and can't be checked here.")
                continue
            if not (css.parent / unquote(parsed.path)).resolve().exists():
                add("missing-file", rel, f"`{value}` doesn't exist.")

    assets = project / "assets"
    if assets.is_dir():
        for asset in sorted(assets.rglob("*")):
            if asset.is_file() and not image_signature_ok(asset):
                add("bad-image", asset.relative_to(project).as_posix(),
                    f"The file isn't really a {asset.suffix.lstrip('.').upper()} image.")

    return sorted(set(issues), key=lambda issue: (issue[1], issue[0], issue[2]))
