"""The themes a project defines, found in its CSS.

A theme is a rule that points the colour roles (or the browser's own colour scheme) elsewhere under an attribute or class on the page root or <body>
(`:root[data-theme="light"] .pbly`, `.pbly[data-theme="dark"]`, `html.dark .pbly`), or under the visitor's
colour-scheme setting. The browser check renders each one as well as the default; DESIGN-SYSTEM.html can switch
between them.
"""
from __future__ import annotations

import re
from pathlib import Path

from naming import namespace_for

THEME_ROOT = re.compile(r"""^(:root|html|body)?((?:\[[\w-]+(?:\s*=\s*["']?[\w-]+["']?)?\]|\.[A-Za-z][\w-]*)+)$""")
THEME_PART = re.compile(r"""\[([\w-]+)(?:\s*=\s*["']?([\w-]+)["']?)?\]|\.([A-Za-z][\w-]*)""")


def css_rules(text):
    """Every innermost CSS rule as (the preludes around it, from outside in; its declarations)."""
    stack, start, rules = [], 0, []
    for i, ch in enumerate(text):
        if ch == "{":
            if stack:
                stack[-1][2] = True
            stack.append([text[start:i].strip(), i + 1, False])
            start = i + 1
        elif ch == "}":
            if stack:
                prelude, body, nested = stack.pop()
                if not nested:
                    rules.append(([p for p, _, _ in stack] + [prelude], text[body:i]))
            start = i + 1
        elif ch == ";":
            start = i + 1
    return rules


def theme_rules(project):
    """Each rule of the project's CSS that defines a theme, as (the rule as CSS, the themes it defines)."""
    project = Path(project)
    namespace = namespace_for(project / "tokens")
    marker = f"--{namespace}-color-"
    found_rules = []
    for css in sorted((project / "css").rglob("*.css")):
        text = re.sub(r"/\*.*?\*/", "", css.read_text(encoding="utf-8"), flags=re.S)
        for preludes, body in css_rules(text):
            if marker not in body and "color-scheme" not in body:
                continue
            themes = []
            if any(p.startswith("@media") and "prefers-color-scheme" in p for p in preludes[:-1]):
                themes.append(("scheme", {"kind": "scheme", "label": "prefers-color-scheme: dark", "name": "dark"}))
            for selector in preludes[-1].split(","):
                first = selector.strip().split()[0] if selector.strip() else ""
                found = THEME_ROOT.match(first)
                if not found:
                    continue
                element, qualifiers = found.group(1), found.group(2)
                if element is None and qualifiers.startswith("."):  # `.pbly.dark`: the first class is the element
                    element, qualifiers = re.match(r"(\.[A-Za-z][\w-]*)(.*)", qualifiers).groups()
                if not qualifiers or element not in (None, ":root", "html", "body", f".{namespace}"):
                    continue  # the scope itself, or a section with its own colours
                target = "body" if element in ("body", f".{namespace}") else "root"
                for attribute, value, cls in THEME_PART.findall(qualifiers):
                    if cls:
                        themes.append(((target, "class", cls), {"kind": "class", "target": target, "name": cls,
                                                                "label": f'class "{cls}"'}))
                    else:
                        shown = f'{attribute}="{value}"' if value else attribute
                        themes.append(((target, attribute, value), {"kind": "attribute", "target": target,
                                                                    "name": attribute, "value": value, "label": shown}))
            if themes:
                css_text = f"{preludes[-1]} {{{body}}}"
                for prelude in reversed(preludes[:-1]):
                    css_text = f"{prelude} {{ {css_text} }}"
                found_rules.append((css_text, themes))
    return found_rules


def project_themes(project):
    """The themes the project's CSS defines by pointing its colour roles elsewhere, beyond the default."""
    themes = {}
    for _, found in theme_rules(project):
        themes.update(found)
    return list(themes.values())
