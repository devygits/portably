"""Run every Portably check on a project and return plain-language issues."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from analyze_tokens import classify_unused, load_policy, unused_tokens
from build_tokens import emitted_variables, generate, reference
from check_handoff import inspect_project
from check_system import html_pages, inspect_system, load_system, parse_css, sources
from colors import chroma, contrast, over, passing_shade
from design_doc import config_of, write_design_doc
from naming import default_namespace, namespace_for, portably_version, replace_namespace
from report import Issue

ROOT = Path(__file__).resolve().parents[1]
FOUNDATION_FILES = ("system.css", "layers.css", "reset.css", "button.css", "accessibility.css")
REQUIRED_PATHS = ("index.html", "tokens/tokens.json", "css/project.css", "css/base.css", "css/layout.css",
                  "css/components.css", "css/pages.css", "js", "assets", "portably.config.json")
PROJECT_IMPORTS = ["base.css", "layout.css", "components.css", "pages.css"]
PAGE_STYLESHEETS = ("foundation/system.css", "tokens/tokens.css", "css/project.css")


class ProjectError(Exception):
    """The folder can't be checked at all; the message says why in plain words."""


@dataclass
class CheckResult:
    project: Path
    issues: list = field(default_factory=list)
    updated: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    exceptions: list = field(default_factory=list)


def find_project(path):
    path = Path(path).resolve()
    if path.is_file():
        path = path.parent
    if path.name == "tokens" and (path / "tokens.json").is_file():
        path = path.parent
    if not path.is_dir():
        raise ProjectError(f"There is no folder at {path}.")
    if not (path / "tokens" / "tokens.json").is_file():
        raise ProjectError(f"{path} doesn't look like a Portably project: it has no tokens/tokens.json.\n"
                           f"Create a project with: python portably.py init <folder>")
    return path


def css_imports(text):
    return re.findall(r'@import\s+url\(["\']([^"\']+)["\']\)\s*;', text)


def canonical_foundation(namespace):
    """The foundation files a project with this namespace should contain."""
    source = default_namespace()
    return {name: replace_namespace((ROOT / "foundation" / name).read_text(encoding="utf-8"), source, namespace)
            for name in FOUNDATION_FILES}


class PageSetup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.body_classes = None
        self.stylesheets = []

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag == "body":
            self.body_classes = (data.get("class") or "").split()
        if tag == "link" and "stylesheet" in (data.get("rel") or "").split() and data.get("href"):
            self.stylesheets.append(data["href"].split("?", 1)[0].split("#", 1)[0].replace("\\", "/"))


def structure_issues(project, namespace):
    issues = []
    for rel in REQUIRED_PATHS:
        if not (project / rel).exists():
            issues.append(Issue("missing-path", rel, f"`{rel}` is missing."))

    expected = canonical_foundation(namespace)
    for name, text in expected.items():
        path = project / "foundation" / name
        if not path.is_file():
            issues.append(Issue("foundation-changed", f"foundation/{name}", "This foundation file is missing.", fixable=True))
        elif path.read_text(encoding="utf-8") != text:
            issues.append(Issue("foundation-changed", f"foundation/{name}",
                                "This file differs from the Portably original.", fixable=True))

    entry = project / "css/project.css"
    if entry.is_file() and css_imports(entry.read_text(encoding="utf-8")) != PROJECT_IMPORTS:
        found = ", ".join(css_imports(entry.read_text(encoding="utf-8"))) or "nothing"
        issues.append(Issue("css-entry", "css/project.css", f"It imports {found}."))
    css_dir = project / "css"
    for path in sorted(css_dir.rglob("*.css")) if css_dir.is_dir() else []:
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            if re.match(r"\s*@layer\b", line):
                issues.append(Issue("css-layer", f"{path.relative_to(project).as_posix()}:{number}", line.strip()))

    for page in html_pages(project):
        rel = page.relative_to(project).as_posix()
        parser = PageSetup()
        parser.feed(page.read_text(encoding="utf-8"))
        if parser.body_classes is not None and namespace not in parser.body_classes:
            issues.append(Issue("page-setup", rel, f"<body> doesn't have the `{namespace}` class."))
        depth = rel.count("/")
        prefix = "../" * depth
        wanted = [prefix + sheet for sheet in PAGE_STYLESHEETS]
        if parser.stylesheets[:3] != wanted:
            loaded = ", ".join(parser.stylesheets[:3]) or "no stylesheets"
            issues.append(Issue("page-setup", rel, f"It loads {loaded}; it should start with {', '.join(wanted)}."))
    return issues


def token_file_issues(token_dir, namespace, write):
    """Read tokens.json, regenerate tokens.css, and return (source or None, issues, updated)."""
    source_path = token_dir / "tokens.json"
    try:
        source = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [Issue("token-error", f"tokens/tokens.json:{exc.lineno}",
                            f"The file isn't valid JSON: {exc.msg.lower()} (line {exc.lineno}, column {exc.colno}).")], []
    issues = []
    for key, value in source.get("space", {}).items():
        if not key.startswith("$") and isinstance(value, dict) and (value.get("$value") or {}).get("unit") != "rem":
            issues.append(Issue("tokens", "tokens/tokens.json", f"`space.{key}` must be written in rem, like the other steps."))
    try:
        css = generate(source, namespace=namespace)
    except (ValueError, KeyError, TypeError) as exc:
        return None, [Issue("token-error", "tokens/tokens.json", f"{exc}.")], []
    updated = []
    target = token_dir / "tokens.css"
    if not target.is_file() or target.read_text(encoding="utf-8") != css:
        if write:
            target.write_text(css, encoding="utf-8")
            updated.append("tokens/tokens.css from tokens.json")
        else:
            issues.append(Issue("token-error", "tokens/tokens.css", "The generated CSS is out of date with tokens.json."))
    return source, issues, updated


def variable_issues(project, source, namespace):
    declared = set(emitted_variables(source, namespace))
    files = sorted((project / "css").rglob("*.css")) if (project / "css").is_dir() else []
    texts = {path: path.read_text(encoding="utf-8") for path in files}
    for text in texts.values():
        declared |= set(re.findall(rf"(--{re.escape(namespace)}-[\w-]+)\s*:", text))
    pattern = re.compile(rf"var\(\s*(--{re.escape(namespace)}-[\w-]+)\s*([,)])")
    issues = []
    for path, text in texts.items():
        for number, line in enumerate(text.splitlines(), 1):
            for name, closer in pattern.findall(line):
                if closer == ")" and name not in declared:
                    issues.append(Issue("unknown-variable", f"{path.relative_to(project).as_posix()}:{number}",
                                        f"`{name}` isn't a token.", snippet=line.strip()))
    return issues


def system_issues(project, token_dir):
    issues = []
    findings, exceptions, stale = inspect_system(project)
    for finding in findings + stale:
        where = finding.file if not finding.line else f"{finding.file}:{finding.line}"
        detail = finding.message
        if finding.kind == "tokens":
            where = "tokens/tokens.json"
        issues.append(Issue(finding.kind, where, detail, snippet=finding.snippet if finding.kind != "tokens" else "",
                            fixable=finding.fixable, command=finding.command, places=finding.places))
    unused, _, _, _ = unused_tokens(token_dir, [project])
    _, unexpected = classify_unused(unused, load_policy())
    for token in unexpected:
        issues.append(Issue("unused-token", "tokens/tokens.json", f"`{token}` isn't used anywhere."))
    return issues, exceptions


CONTRAST_PAIRS = (
    # (foreground role, background role, ratio needed, what the pair is for)
    ("color.text.primary", "color.background", 4.5, "text"),
    ("color.text.primary", "color.surface.raised", 4.5, "text"),
    ("color.text.muted", "color.background", 4.5, "text"),
    ("color.text.muted", "color.surface.raised", 4.5, "text"),
    ("color.text.soft", "color.background", 4.5, "text"),
    ("color.text.soft", "color.surface.raised", 4.5, "text"),
    ("color.action.on-primary", "color.action.primary", 4.5, "button text"),
    ("color.action.on-primary", "color.action.hover", 4.5, "button text on hover"),
    ("color.action.primary", "color.background", 3, "a button against the page"),
    ("color.border.strong", "color.background", 3, "form field borders"),
    ("color.border.strong", "color.surface.raised", 3, "form field borders"),
)


ROOT_SELECTOR = re.compile(r"^(?:html|:root)$")
ROOT_SIZES = {"100%", "16px", "1rem", "medium", "1em"}


def root_size_issues(project):
    """Every rem token assumes the browser's 16px root; a page that changes it rescales the whole system."""
    issues = []
    for block in sources(project):
        for d in parse_css(block.text)[0]:
            selectors = [part.strip() for part in d.selector.split(",")]
            if d.prop == "font-size" and any(ROOT_SELECTOR.match(part) for part in selectors) \
                    and d.value.strip().lower() not in ROOT_SIZES:
                rel = block.path.relative_to(project).as_posix()
                issues.append(Issue("root-size", f"{rel}:{block.line + d.line - 1}",
                                    f"`{d.selector} {{ font-size: {d.value} }}` makes every rem token a different size "
                                    f"from what tokens.json and DESIGN-SYSTEM.md say."))
    return issues


def contrast_issues(system):
    """Check the colour pairs every Portably project relies on, without needing a browser."""
    issues = []
    for fg, bg, need, purpose in CONTRAST_PAIRS:
        if fg not in system.colors or bg not in system.colors:
            continue
        (bg_rgb, bg_alpha), (fg_rgb, fg_alpha) = system.colors[bg], system.colors[fg]
        base = over(bg_rgb, bg_alpha, (255, 255, 255))
        ratio = contrast(over(fg_rgb, fg_alpha, base), base)
        if ratio < need - 0.005:
            # Suggest a new shade for the more colourful of the two (usually the brand colour), else the foreground.
            fg_solid = over(fg_rgb, fg_alpha, base)
            change, keep = (bg, fg_solid) if chroma(base) > chroma(fg_solid) + 0.01 else (fg, base)
            source = source_token(system.tokens, change)
            shade = passing_shade(base if change == bg else fg_solid, keep, need)
            hint = f" The closest shade that passes: `{source}` → {shade}." if shade else ""
            issues.append(Issue("contrast-roles", "tokens/tokens.json",
                                f"`{fg}` on `{bg}` ({purpose}) is {ratio:.1f}:1; it needs {need:g}:1.{hint}"))
    return issues


def source_token(tokens, path):
    """The token that actually holds the value: follow aliases such as {color.palette.green}."""
    seen = set()
    while path in tokens and path not in seen:
        seen.add(path)
        target = reference(tokens[path]["$value"])
        if not target or target not in tokens:
            break
        path = target
    return path


def handoff_issues(project):
    return [Issue(group, where, detail, fixable=group == "handoff-file") for group, where, detail in inspect_project(project)]


NOTE_LISTS = ("assumptions", "deviations", "normalizations", "readability")


def context_issues(project):
    """The design context in portably.config.json: which Portably it follows and where the design came from."""
    config = config_of(project)
    issues = []
    version, recorded = portably_version(), config.get("portably")
    if not isinstance(recorded, str) or recorded.split(".")[0] != version.split(".")[0]:
        detail = (f"It records Portably {recorded}; this is Portably {version}." if recorded else
                  f"It doesn't record which Portably version it follows; this is Portably {version}.")
        issues.append(Issue("version", "portably.config.json", detail))
    source = config.get("source")
    if isinstance(source, list):
        source = " ".join(item for item in source if isinstance(item, str))
    if not isinstance(source, str) or not source.strip():
        issues.append(Issue("source", "portably.config.json", "There is no \"source\"."))
    for key in NOTE_LISTS:
        value = config.get(key, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            issues.append(Issue("context-format", "portably.config.json", f"\"{key}\" isn't a list of sentences."))
    return issues


def framework_issues():
    """Checks for maintaining Portably itself: the starter, foundation and docs must agree."""
    from framework import framework_problems
    return [Issue("framework", where, detail) for where, detail in framework_problems()]


def run_check(path, framework=False, browser=True, write=True):
    project = find_project(path)
    token_dir = project / "tokens"
    result = CheckResult(project)
    try:
        namespace = namespace_for(token_dir)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ProjectError(f"portably.config.json can't be read: {exc}") from exc

    source, issues, updated = token_file_issues(token_dir, namespace, write)
    result.issues += issues
    result.updated += updated
    result.issues += structure_issues(project, namespace)
    if source is not None:
        result.issues += variable_issues(project, source, namespace)
        try:
            found, result.exceptions = system_issues(project, token_dir)
            result.issues += found
            result.issues += contrast_issues(load_system(project)[0])
            result.issues += root_size_issues(project)
        except ValueError as exc:
            result.issues.append(Issue("token-error", "tokens/tokens.json", f"{exc}."))
            source = None
    result.issues += handoff_issues(project)
    result.issues += context_issues(project)

    if browser:
        from check_browser import browser_issues
        found, skipped = browser_issues(project)
        missing = {i.detail.split("`")[1] for i in result.issues if i.group == "missing-file" and "`" in i.detail}
        result.issues += [i for i in found if not (i.group == "image-failed" and i.detail.split("`")[1] in missing)]
        result.skipped += skipped
    else:
        result.skipped.append("Browser checks (sideways scrolling, images that fail to load, contrast on screen) were turned off.")

    if framework:
        result.issues += framework_issues()

    if source is not None and write:
        system, _ = load_system(project)
        result.updated += write_design_doc(project, system, result.exceptions)
    return result
