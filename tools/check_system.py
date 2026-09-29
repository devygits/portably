"""Check that a Portably project follows its design system.

Design values in project CSS (and inline HTML styles) must come from
tokens.json. A value close to a token is a small inconsistency to snap; a
deliberate one-off carries `/* exception: reason */` on the same line; a value
needed in two or more places becomes a token. Every judgement also says how
to fix it, so `portably fix` and `portably promote` can rewrite the CSS.
"""
from __future__ import annotations

import bisect
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from analyze_tokens import resolve_token_directory
from build_tokens import collect, css_name, reference
from colors import COLOR_FUNC, HEX, parse_color, token_rgba
from naming import namespace_for

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "standard/system-policy.json").read_text(encoding="utf-8"))
SPACING = json.loads((ROOT / "standard/spacing-scale.json").read_text(encoding="utf-8"))
BREAKPOINTS = json.loads((ROOT / "standard/breakpoints.json").read_text(encoding="utf-8"))["breakpoints"]
ROOT_PX = POLICY["nominalRootPx"]
SNAP = POLICY["snap"]

COMMENT = re.compile(r"/\*.*?\*/", re.S)
EXCEPTION = re.compile(r"exception\s*:\s*(\S[^*]*)", re.I)
LENGTH = re.compile(r"(?<![\w#.-])(-?\d*\.?\d+)(px|rem|em)\b", re.I)
NUMBER = re.compile(r"-?\d*\.?\d+\Z")
SPACING_PROP = re.compile(
    r"(?:margin|padding)(?:-(?:top|right|bottom|left|block|inline)(?:-(?:start|end))?)?\Z|(?:row-|column-)?gap\Z"
)
RADIUS_PROP = re.compile(r"border(?:-(?:top|bottom|start|end)-(?:left|right|start|end))?-radius\Z")
SHADOW_PROPS = {"box-shadow", "text-shadow"}
SPACING_KEY = re.compile(r"(\d+)(-5)?\Z")
NO_VARIABLES = ("@font-face", "@property")
STYLE_ATTR = re.compile(r"""\sstyle\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
STYLE_ELEMENT = re.compile(r"<style\b[^>]*>(.*?)</style\s*>", re.I | re.S)
HTML_SKIP = re.compile(r"<!--.*?-->|<script\b.*?</script\s*>", re.I | re.S)
SIZE_NAMES = ("3xs", "2xs", "xs", "sm", "base", "md", "lg", "xl", "2xl", "3xl", "4xl", "5xl", "6xl", "7xl", "8xl")

# Kinds whose value is outside the system and needs a person's decision.
DECISION_KINDS = {"off-system", "shadow", "breakpoint"}


@dataclass
class Judgement:
    """What one hand-written value means for the design system, and how to fix it."""
    kind: str
    message: str
    key: tuple | None = None
    literal: str | None = None
    replacement: str | None = None
    token: str | None = None


@dataclass
class Finding:
    file: str
    line: int
    kind: str
    snippet: str
    message: str
    key: tuple | None = None
    fixable: bool = False
    places: list = field(default_factory=list)
    command: str | None = None


@dataclass
class RecordedException:
    file: str
    line: int
    snippet: str
    reason: str
    keys: tuple


@dataclass
class Declaration:
    prop: str
    value: str
    line: int
    exception: str | None
    value_span: tuple = (0, 0)
    comment_span: tuple | None = None
    selector: str = ""


@dataclass
class MediaQuery:
    prelude: str
    line: int
    exception: str | None
    comment_span: tuple | None = None


@dataclass
class Block:
    """CSS text inside a project file: a whole stylesheet, a <style> element or a style attribute."""
    path: Path
    text: str
    offset: int
    line: int


def dimension_px(value):
    if value["unit"] == "em":
        raise ValueError(f"{value['value']:g}em: `em` works only for letter spacing (font.tracking.*); use px or rem")
    return value["value"] * (ROOT_PX if value["unit"] == "rem" else 1)


def tracking_value(number, unit):
    """Letter spacing in comparable form: ("em", 0.02) or ("px", 1.5)."""
    unit = unit.lower()
    if unit == "em":
        return "em", float(number)
    return "px", float(number) * (ROOT_PX if unit == "rem" else 1)


def shadow_from_token(value):
    lengths = tuple(dimension_px(value[k]) for k in ("offsetX", "offsetY", "blur", "spread"))
    rgb, alpha = token_rgba(value["color"])
    return lengths, rgb, alpha, bool(value.get("inset"))


def parse_shadow(text):
    """Read one hand-written shadow like '0 4px 12px rgba(0, 0, 0, .08)'. None when it's several or unreadable."""
    text = text.strip()
    if not text or "," in COLOR_FUNC.sub("", text) or "var(" in text:
        return None
    inset = bool(re.search(r"\binset\b", text, re.I))
    colors = [m.group() for m in HEX.finditer(text)] + [m.group() for m in COLOR_FUNC.finditer(text)]
    if len(colors) != 1:
        return None
    rest = re.sub(r"\binset\b", " ", COLOR_FUNC.sub(" ", HEX.sub(" ", text)), flags=re.I).split()
    lengths = []
    for part in rest:
        found = re.fullmatch(r"(-?\d*\.?\d+)(px|rem)?", part, re.I)
        if not found or (found.group(2) is None and float(found.group(1)) != 0):
            return None
        lengths.append(float(found.group(1)) * (ROOT_PX if (found.group(2) or "").lower() == "rem" else 1))
    if not 2 <= len(lengths) <= 4:
        return None
    parsed = parse_color(colors[0])
    if parsed is None:
        return None
    return tuple(lengths + [0.0] * (4 - len(lengths))), parsed[0], parsed[1], inset


class System:
    """The project's resolved design values, grouped by what they govern."""

    def __init__(self, source, namespace):
        self.namespace = namespace
        self.tokens = collect(source)
        self.spacing, self.font_size, self.radius, self.line_height, self.weight, self.colors, self.shadows = (
            {} for _ in range(7))
        self.tracking = {}  # path -> (unit, value): "em" values, or "px" for px and rem
        for path in self.tokens:
            token = self.resolve(path)
            kind, value = token["$type"], token["$value"]
            if kind == "dimension" and path.startswith("space."):
                self.spacing[path] = dimension_px(value)
            elif kind == "dimension" and path.startswith("font.size."):
                self.font_size[path] = dimension_px(value)
            elif kind == "dimension" and path.startswith("font.tracking."):
                self.tracking[path] = tracking_value(value["value"], value["unit"])
            elif kind == "dimension" and path.startswith("radius."):
                self.radius[path] = dimension_px(value)
            elif kind == "number" and path.startswith("font.line-height."):
                self.line_height[path] = float(value)
            elif kind == "fontWeight":
                self.weight[path] = float(value)
            elif kind == "color":
                self.colors[path] = token_rgba(value)
            elif kind == "shadow" and isinstance(value, dict):
                self.shadows[path] = shadow_from_token(value)
        self.variables = {css_name(path, namespace) for path in self.tokens}

    def resolve(self, path, seen=()):
        token = self.tokens[path]
        target = reference(token["$value"])
        if target is None:
            return token
        if target in seen or target not in self.tokens:
            raise ValueError(f"Unresolvable token alias: {path} -> {target}")
        return self.resolve(target, seen + (path,))

    def var(self, path):
        return f"var({css_name(path, self.namespace)})"


def blank_comments(text, comments):
    chars = list(text)
    for start, end, _ in comments:
        for i in range(start, end):
            if chars[i] != "\n":
                chars[i] = " "
    return "".join(chars)


def parse_css(text):
    """Split CSS into declarations and @media preludes, keeping positions and exception comments."""
    comments = [(m.start(), m.end(), m.group()) for m in COMMENT.finditer(text)]
    clean = blank_comments(text, comments)
    line_starts = [0] + [m.end() for m in re.finditer("\n", text)]

    def line_of(pos):
        return bisect.bisect_right(line_starts, pos)

    def exception_for(start, end, own_line=False):
        """The exception comment for the declaration at start..end: inside it, or right after it on the same line.

        A comment that follows another declaration on the line belongs to that one instead.
        """
        newline = text.find("\n", end)
        limit = len(text) if newline < 0 else newline
        for c_start, c_end, body in comments:
            if not own_line and c_start > end and clean[end:c_start].strip(" \t;}"):
                continue
            if start <= c_start <= limit:
                found = EXCEPTION.search(body)
                if found:
                    return found.group(1).strip(), (c_start, c_end)
        return None, None

    declarations, media, blocks = [], [], []
    depth, quote, buffer_start = 0, None, 0

    def add_declaration(start, end):
        raw = clean[start:end]
        stripped = raw.strip()
        if not stripped or stripped.startswith("@") or ":" not in stripped:
            return
        if any(block.startswith(NO_VARIABLES) for block in blocks):
            return
        prop, value = stripped.split(":", 1)
        prop = prop.strip().lower()
        if not re.fullmatch(r"-{0,2}[a-z][\w-]*", prop):
            return
        begin = start + len(raw) - len(raw.lstrip())
        value_start = begin + stripped.index(":") + 1
        value_start += len(value) - len(value.lstrip())
        value_end = value_start + len(value.strip())
        reason, span = exception_for(begin, end)
        declarations.append(Declaration(prop, value.strip(), line_of(begin), reason, (value_start, value_end), span,
                                        blocks[-1] if blocks else ""))

    for i, ch in enumerate(clean):
        if quote:
            if ch == quote and clean[i - 1] != "\\":
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth:
            continue
        elif ch == "{":
            raw = clean[buffer_start:i]
            begin = buffer_start + len(raw) - len(raw.lstrip())
            if raw.strip().lower().startswith("@media"):
                reason, span = exception_for(begin, begin, own_line=True)
                media.append(MediaQuery(raw.strip(), line_of(begin), reason, span))
            blocks.append(raw.strip().lower())
            buffer_start = i + 1
        elif ch in ";}":
            add_declaration(buffer_start, i)
            if ch == "}" and blocks:
                blocks.pop()
            buffer_start = i + 1
    add_declaration(buffer_start, len(clean))
    return declarations, media


GENERATED_PAGE = "DESIGN-SYSTEM.html"  # written by `check`; not one of the project's pages


def html_pages(project):
    pages = [page for page in project.glob("*.html") if page.name != GENERATED_PAGE]
    page_dir = project / "pages"
    if page_dir.is_dir():
        pages.extend(page_dir.rglob("*.html"))
    return sorted(set(pages))


def html_blocks(path, text):
    skipped = [(m.start(), m.end()) for m in HTML_SKIP.finditer(text)]

    def hidden(pos):
        return any(start <= pos < end for start, end in skipped)

    found = []
    for match in STYLE_ELEMENT.finditer(text):
        if not hidden(match.start()):
            found.append((match.start(1), match.group(1)))
    for match in STYLE_ATTR.finditer(text):
        if hidden(match.start()):
            continue
        group = 1 if match.group(1) is not None else 2
        found.append((match.start(group), match.group(group)))
    for offset, css in sorted(found):
        yield Block(path, css, offset, text.count("\n", 0, offset) + 1)


def sources(project):
    """Every piece of CSS the project writes by hand, with its position in its file."""
    css_dir = project / "css"
    for path in sorted(css_dir.rglob("*.css")) if css_dir.is_dir() else []:
        yield Block(path, path.read_text(encoding="utf-8"), 0, 1)
    for page in html_pages(project):
        yield from html_blocks(page, page.read_text(encoding="utf-8"))


def strip_calls(value, name):
    """Remove name(...) calls, honouring nested parentheses; return (remaining text, list of call bodies)."""
    out, bodies, pos = [], [], 0
    pattern = re.compile(rf"\b{name}\(", re.I)
    while True:
        found = pattern.search(value, pos)
        if not found:
            out.append(value[pos:])
            return "".join(out), bodies
        depth, end = 0, found.end() - 1
        for end in range(found.end() - 1, len(value)):
            depth += {"(": 1, ")": -1}.get(value[end], 0)
            if depth == 0:
                break
        out.append(value[pos:found.start()] + " ")
        bodies.append(value[found.end():end])
        pos = end + 1


def to_lab(rgb):
    def linear(channel):
        channel /= 255
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in rgb)
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a, b):
    return sum((p - q) ** 2 for p, q in zip(to_lab(a), to_lab(b))) ** 0.5


def fmt(number):
    return f"{number:g}"


def color_key(rgb, alpha):
    return ("colour", tuple(round(c) for c in rgb), alpha)


# The roles a property may take. Action colours fit all three (link text, button fill, outline button).
# "On" colours (action.on-primary) are only right on top of an action colour, which fix can't see, so it never picks them.
COLOR_FAMILIES = (
    (re.compile(r"color\Z"), ("color.text.", "color.action.primary", "color.action.hover")),
    (re.compile(r"background(?:-color)?\Z"), ("color.background", "color.surface.", "color.action.primary", "color.action.hover")),
    (re.compile(r"(?:border|outline)"), ("color.border.", "color.action.primary", "color.action.hover")),
)


def pick_color(prop, matches):
    """Choose the one token a colour should become, or None when a person has to pick.

    A role is only chosen when it fits the property: text colour never becomes a border role, and so on. Otherwise the
    plain palette colour is used, because it says nothing about where the colour belongs.
    """
    roles = [m for m in matches if not m.startswith("color.palette.")]
    palette = [m for m in matches if m.startswith("color.palette.")]
    for pattern, prefixes in COLOR_FAMILIES:
        if pattern.match(prop):
            family = [r for r in roles if r.startswith(prefixes)]
            if len(family) == 1:
                return family[0]
            if family:
                return None
            break
    return palette[0] if len(palette) == 1 else None


def judge_color(literal, system, prop=""):
    parsed = parse_color(literal)
    if parsed is None:
        return None
    rgb, alpha = parsed
    key = color_key(rgb, alpha)
    same_alpha = [(delta_e(rgb, value), path) for path, (value, a) in system.colors.items() if abs(a - alpha) < 0.01]
    opaque = [(delta_e(rgb, value), path) for path, (value, a) in system.colors.items() if a == 1]
    translucent = alpha < 1 and not (same_alpha and min(same_alpha)[0] <= SNAP["colorDeltaE"])
    candidates = opaque if translucent else same_alpha
    if not candidates:
        return Judgement("off-system", f"`{literal}` is not one of the project's colours.", key, literal)
    best = min(d for d, _ in candidates)
    matches = sorted({p for d, p in candidates if abs(d - best) < 1e-9}, key=lambda p: (p.startswith("color.palette."), p))
    if best > SNAP["colorDeltaE"]:
        return Judgement("off-system", f"`{literal}` is not one of the project's colours (closest: `{matches[0]}`).", key, literal)
    kind = "token-value" if best < 0.05 else "snap"
    percent = fmt(round(alpha * 100, 1))
    choice = pick_color(prop, matches)
    shown = " / ".join(f"`{m}`" for m in matches[:4]) + (f" at {percent}% opacity" if translucent else "")
    relation = "is" if kind == "token-value" else "looks the same as"
    if choice is None:
        return Judgement(kind, f"`{literal}` {relation} {shown}: pick the role that fits.", None, literal)
    write = system.var(choice)
    if translucent:
        write = f"color-mix(in srgb, {write} {percent}%, transparent)"
    return Judgement(kind, f"`{literal}` {relation} `{choice}`" + (f" at {percent}% opacity" if translucent else "") + ".",
                     None, literal, write, choice)


def spacing_step_name(px):
    steps = px / 4
    if abs(steps * 2 - round(steps * 2)) > 1e-9:
        return None
    whole = int(steps)
    return f"space.{whole}" + ("-5" if steps != whole else "")


def judge_length(number, unit, scale, snap_px, label, system, what):
    literal = f"{number}{unit}"
    if unit.lower() == "em":
        return Judgement("off-system", f"`{literal}` is relative to the text size, so it can't follow the {what}.",
                         (label, literal), literal)
    px = abs(float(number)) * (ROOT_PX if unit.lower() == "rem" else 1)
    if px == 0:
        return None
    options = {path: value for path, value in scale.items() if value > 0}
    if not options:
        return Judgement("off-system", f"`{literal}` has no {what} to follow.", (label, px), literal)
    path, value = min(options.items(), key=lambda item: (abs(item[1] - px), -item[1]))
    token = system.var(path)
    if float(number) < 0:
        token = f"calc(-1 * {token})"
    diff = abs(value - px)
    if diff < 1e-6:
        return Judgement("token-value", f"`{literal}` is `{path}`.", None, literal, token, path)
    if px < min(options.values()):
        return Judgement("off-system", f"`{literal}` is smaller than the smallest step in the {what}; "
                                       f"hairline adjustments are usually deliberate.", (label, px), literal)
    if diff <= snap_px:
        return Judgement("snap", f"`{literal}` is {fmt(diff)}px from `{path}` ({fmt(value)}px).", None, literal, token, path)
    return Judgement("off-system", f"`{literal}` is not in the {what} (closest: `{path}`, {fmt(value)}px).",
                     (label, px), literal)


def judge_shadow(prop, value, system):
    written = re.sub(r"\s+", " ", re.sub(r"!\s*important\s*\Z", "", value, flags=re.I).strip())
    parsed = parse_shadow(written) if prop == "box-shadow" else None
    if parsed:
        lengths, rgb, alpha, inset = parsed
        near = None
        for path, (t_lengths, t_rgb, t_alpha, t_inset) in system.shadows.items():
            if t_inset != inset:
                continue
            gap = max(abs(a - b) for a, b in zip(lengths, t_lengths))
            colour = delta_e(rgb, t_rgb)
            if gap < 1e-6 and colour < 0.05 and abs(alpha - t_alpha) < 0.005:
                return Judgement("token-value", f"This shadow is `{path}`.", None, written, system.var(path), path)
            if near is None and gap <= 1 and colour <= SNAP["colorDeltaE"] and abs(alpha - t_alpha) <= 0.02:
                near = path
        if near:
            return Judgement("snap", f"This shadow looks the same as `{near}`.", None, written, system.var(near), near)
    advice = "use shadow.sm, shadow.md or shadow.lg" if prop == "box-shadow" else "there is no text-shadow token"
    return Judgement("shadow", f"`{prop}` is written by hand ({advice}).", ("shadow", written))


def judge_tracking(number, unit, system):
    literal = f"{number}{unit}"
    kind, value = tracking_value(number, unit)
    options = {path: v for path, (k, v) in system.tracking.items() if k == kind}
    key = ("letter spacing", literal.lower())
    if not options:
        return Judgement("off-system", f"`{literal}` has no letter-spacing token in {kind}.", key, literal)
    path, token_value = min(options.items(), key=lambda item: abs(item[1] - value))
    diff = abs(token_value - value)
    shown = f"{fmt(token_value)}{kind}"
    if diff < 1e-4:
        return Judgement("token-value", f"`{literal}` is `{path}`.", None, literal, system.var(path), path)
    if diff <= (0.005 if kind == "em" else 0.25):
        return Judgement("snap", f"`{literal}` is {fmt(round(diff, 3))}{kind} from `{path}` ({shown}).",
                         None, literal, system.var(path), path)
    return Judgement("off-system", f"`{literal}` is not one of the letter-spacing tokens (closest: `{path}`, {shown}).",
                     key, literal)


def judge_number(text, scale, label, system, what, neutral, snap=0.0):
    value = float(text)
    if value in neutral:
        return None
    for path, token_value in scale.items():
        if abs(token_value - value) < 1e-3:
            return Judgement("token-value", f"`{text}` is `{path}`.", None, text, system.var(path), path)
    if scale and snap:
        path, token_value = min(scale.items(), key=lambda item: (abs(item[1] - value), -item[1]))
        if abs(token_value - value) <= snap + 1e-9:
            return Judgement("snap", f"`{text}` is {fmt(round(abs(token_value - value), 3))} from `{path}` "
                                     f"({fmt(token_value)}).", None, text, system.var(path), path)
    closest = min(scale, key=lambda p: abs(scale[p] - value)) if scale else None
    hint = f" (closest: `{closest}`, {fmt(scale[closest])})" if closest else ""
    return Judgement("off-system", f"`{text}` is not in the {what}{hint}.", (label, value), text)


def declaration_findings(decl, system):
    """Yield a Judgement for every design value in one declaration."""
    prop = decl.prop
    value = re.sub(r"!\s*important\s*\Z", "", decl.value, flags=re.I).strip()
    bare, var_bodies = strip_calls(value, "var")
    bare, _ = strip_calls(bare, "url")
    bare = re.sub(r"\"[^\"]*\"|'[^']*'", " ", bare)

    for body in var_bodies:
        name, comma, fallback = body.partition(",")
        name = name.strip()
        if comma and name in system.variables and fallback.strip():
            yield Judgement("fallback", f"`var({name}, {fallback.strip()})` keeps a copy of the token's value.",
                            None, f"var({body})", f"var({name})")

    colors = [m.group() for m in HEX.finditer(bare)] + [m.group() for m in COLOR_FUNC.finditer(bare)]
    no_colors = COLOR_FUNC.sub(" ", HEX.sub(" ", bare))
    lengths = [(m.group(1), m.group(2)) for m in LENGTH.finditer(no_colors) if float(m.group(1)) != 0]

    if prop.startswith("--"):
        if colors or lengths:
            shown = ", ".join(colors + [n + u for n, u in lengths])
            if prop.startswith(f"--{system.namespace}-"):
                message = f"`{prop}` is overridden with a raw value ({shown}) instead of a token."
            else:
                message = f"`{prop}` holds a raw design value ({shown})."
            yield Judgement("hidden-token", message, ("custom property", prop, shown))
        return

    if prop in SHADOW_PROPS:
        if colors or lengths:
            yield judge_shadow(prop, value, system)
        return

    for literal in colors:
        judged = judge_color(literal, system, prop)
        if judged:
            yield judged

    if SPACING_PROP.match(prop):
        for number, unit in lengths:
            yield judge_length(number, unit, system.spacing, SNAP["spacingPx"], "spacing", system, "spacing scale")
    elif RADIUS_PROP.match(prop):
        for number, unit in lengths:
            yield judge_length(number, unit, system.radius, SNAP["radiusPx"], "radius", system, "radius scale")
    elif prop == "font-size":
        for number, unit in lengths:
            if unit.lower() == "em" and float(number) == 1:
                continue
            yield judge_length(number, unit, system.font_size, SNAP["fontSizePx"], "font size", system, "type scale")
    elif prop == "line-height":
        if NUMBER.match(bare.strip()):
            yield judge_number(bare.strip(), system.line_height, "line height", system, "line-height scale", {0.0, 1.0},
                               SNAP.get("lineHeight", 0))
        for number, unit in lengths:
            yield Judgement("off-system", f"`{number}{unit}` sets line height in a unit; line-height tokens are unitless.",
                            ("line height", number + unit), number + unit)
    elif prop == "letter-spacing":
        for number, unit in lengths:
            yield judge_tracking(number, unit, system)
    elif prop == "font-weight" and NUMBER.match(bare.strip()):
        yield judge_number(bare.strip(), system.weight, "font weight", system, "font weights", set())


def project_breakpoints(project):
    allowed = {}
    for name, px in BREAKPOINTS.items():
        allowed[px] = name
        allowed[px + 1] = name
    config = project / "portably.config.json"
    if config.is_file():
        extra = json.loads(config.read_text(encoding="utf-8")).get("breakpoints", {})
        for name, px in extra.items():
            allowed[px] = name
            allowed[px + 1] = name
    return allowed


def media_findings(query, allowed):
    names = ", ".join(f"{fmt(px)}px" for px in sorted(allowed) if px - 1 not in allowed)
    for number, unit in LENGTH.findall(query.prelude):
        px = float(number) * (1 if unit.lower() == "px" else ROOT_PX)
        if px not in allowed:
            yield Judgement("breakpoint", f"`{number}{unit}` is not a project breakpoint ({names}).",
                            ("breakpoint", px), number + unit)


def token_findings(system):
    rel = "tokens/tokens.json"
    missing = []
    for group, paths in POLICY["requiredTokens"].items():
        absent = [p for p in paths if p not in system.tokens]
        if absent:
            missing.append(Finding(rel, 0, "tokens", group, f"The {group} are missing {', '.join(f'`{p}`' for p in absent)}."))
    for key, px in SPACING["steps"].items():
        path = f"space.{key}"
        if path not in system.spacing:
            missing.append(Finding(rel, 0, "tokens", path, f"`{path}` ({px}px) is a baseline spacing step and is missing."))
        elif abs(system.spacing[path] - px) > 1e-6:
            missing.append(Finding(rel, 0, "tokens", path,
                                   f"`{path}` must stay {px}px (its name says so); add a new step for a different value."))
    for path, px in system.spacing.items():
        key = path.split(".", 1)[1]
        if key in SPACING["steps"]:
            continue
        expected = spacing_step_name(px)
        if not SPACING_KEY.fullmatch(key) or expected != path:
            suggestion = f"`{expected}`" if expected else "a whole or half 4px step"
            missing.append(Finding(rel, 0, "tokens", path,
                                   f"`{path}` is {fmt(px)}px; spacing steps are named px ÷ 4, so it should be {suggestion}."))
    return missing


def load_system(project):
    token_dir = resolve_token_directory(project)
    source = json.loads((token_dir / "tokens.json").read_text(encoding="utf-8"))
    return System(source, namespace_for(token_dir)), token_dir


@dataclass
class Item:
    """One checked declaration or @media query, with its judgements."""
    block: Block
    line: int
    snippet: str
    exception: str | None
    comment_span: tuple | None
    value_span: tuple | None
    judgements: list
    prop: str = ""

    @property
    def decision_keys(self):
        return tuple(j.key for j in self.judgements if j.kind in DECISION_KINDS and j.key)


def scan(project, system):
    """Judge every hand-written declaration and @media query in the project."""
    allowed = project_breakpoints(project)
    for block in sources(project):
        declarations, media = parse_css(block.text)
        items = []
        for d in declarations:
            judgements = [j for j in declaration_findings(d, system) if j]
            items.append(Item(block, block.line + d.line - 1, re.sub(r"\s+", " ", f"{d.prop}: {d.value}"),
                              d.exception, d.comment_span, d.value_span, judgements, d.prop))
        rebind_line_exceptions(items)
        yield from items
        for q in media:
            judgements = [j for j in media_findings(q, allowed) if j]
            yield Item(block, block.line + q.line - 1, re.sub(r"\s+", " ", q.prelude),
                       q.exception, q.comment_span, None, judgements)


def rebind_line_exceptions(items):
    """A comment at the end of a line excuses the value on that line that needs it.

    parse_css gives the comment to the declaration right before it; when that one follows the system and an
    earlier declaration on the same line doesn't, the comment moves to the earlier one.
    """
    for i, item in enumerate(items):
        if not item.exception or item.decision_keys:
            continue
        for earlier in reversed(items[:i]):
            if earlier.line != item.line:
                break
            if not earlier.exception and earlier.decision_keys:
                earlier.exception, earlier.comment_span = item.exception, item.comment_span
                item.exception, item.comment_span = None, None
                break


def promote_command(key):
    """The `promote` arguments that would add a repeated value to the system, or None."""
    label = key[0]
    if label == "spacing" and isinstance(key[1], (int, float)):
        step = round(key[1] / 2) * 2
        return f"spacing {fmt(step)}px" if step else None  # a hairline can't be a spacing step
    if label in ("radius", "font size") and isinstance(key[1], (int, float)):
        kind, group = ("radius", "radius") if label == "radius" else ("font-size", "font.size")
        return f"{kind} {fmt(key[1])}px --as {group}.NAME"
    if label == "colour" and key[2] == 1:
        return 'colour "#' + "".join(f"{c:02X}" for c in key[1]) + '" --as color.palette.NAME'
    if label == "breakpoint":
        return f"breakpoint {fmt(key[1])}px"
    if label == "line height" and isinstance(key[1], (int, float)):
        return f"line-height {fmt(key[1])} --as font.line-height.NAME"
    if label == "letter spacing":
        if key[1].startswith("-"):  # a value starting with - must come after --, or it reads as an option
            return f"letter-spacing --as font.tracking.NAME -- {key[1]}"
        return f"letter-spacing {key[1]} --as font.tracking.NAME"
    if label == "shadow" and parse_shadow(key[1]):
        return f'shadow "{key[1]}" --as shadow.NAME'
    return None


def describe_key(key):
    label = key[0]
    if label == "colour":
        return "colour #" + "".join(f"{c:02X}" for c in key[1])
    if label in ("spacing", "radius", "font size", "breakpoint") and isinstance(key[1], (int, float)):
        return f"{label} {fmt(key[1])}px"
    if label == "shadow":
        return f"shadow `{key[1]}`"
    return f"{label} {key[1]}"


def inspect_system(project):
    """Return (findings, exceptions, stale) for the project's design system."""
    project = Path(project).resolve()
    token_dir = resolve_token_directory(project)
    project = token_dir.parent
    system, _ = load_system(project)
    findings = token_findings(system)
    exceptions, stale, outside = [], [], []

    for item in scan(project, system):
        rel = item.block.path.relative_to(project).as_posix()
        if item.exception:
            keys = item.decision_keys
            if keys:
                exceptions.append(RecordedException(rel, item.line, item.snippet, item.exception, keys))
            else:
                stale.append(Finding(rel, item.line, "stale-exception", item.snippet,
                                     f"The exception \"{item.exception}\" is no longer needed: the value follows the system.",
                                     fixable=True))
            continue
        for j in item.judgements:
            finding = Finding(rel, item.line, j.kind, item.snippet, j.message, j.key, fixable=j.replacement is not None)
            (outside if j.kind in DECISION_KINDS and j.key else findings).append(finding)

    # A value outside the system used in more than one place (with or without exception comments) is a missing token.
    places = defaultdict(list)
    for finding in outside:
        places[finding.key].append((finding.file, finding.line, finding.snippet, finding))
    for exc in exceptions:
        for key in exc.keys:
            places[key].append((exc.file, exc.line, exc.snippet, None))
    for key, where in places.items():
        uses = [f for *_, f in where if f]
        if len(where) > POLICY["repeatedExceptionLimit"]:
            where.sort(key=lambda place: place[:2])
            first_file, first_line, snippet, _ = where[0]
            findings.append(Finding(first_file, first_line, "promote", snippet,
                                    f"The {describe_key(key)} appears in {len(where)} places.", key,
                                    places=[f"{f}:{line}" for f, line, *_ in where], command=promote_command(key)))
        else:
            for finding in uses:
                finding.command = promote_command(key)
                findings.append(finding)

    findings.sort(key=lambda f: (f.file != "tokens/tokens.json", f.file, f.line))
    return findings, exceptions, stale
