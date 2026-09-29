"""Change a project on request: `portably fix` (safe fixes) and `portably promote` (grow the system)."""
from __future__ import annotations

import json
import re
from collections import defaultdict

from build_tokens import KEY, generate
from check import canonical_foundation, find_project
from check_system import ROOT_PX, SIZE_NAMES, fmt, load_system, parse_shadow, scan, spacing_step_name
from colors import FORMATS, parse_color, to_hex, token_rgba
from naming import namespace_for
from project import HANDOFF_FILES, template


class PromoteError(Exception):
    """The request can't be carried out; the message says why and what to do instead."""


def protected_spans(value):
    """Parts of a value that must never be rewritten: comments, strings, url() and var() calls."""
    spans = [(m.start(), m.end()) for m in re.finditer(r"/\*.*?\*/|\"[^\"]*\"|'[^']*'", value, re.S)]
    for name in ("var", "url"):
        for found in re.finditer(rf"\b{name}\(", value, re.I):
            depth = 0
            for end in range(found.end() - 1, len(value)):
                depth += {"(": 1, ")": -1}.get(value[end], 0)
                if depth == 0:
                    break
            spans.append((found.start(), end + 1))
    return spans


def replace_once(value, literal, replacement):
    """Replace the first occurrence of a hand-written literal that isn't inside a var(), url() or comment."""
    if literal.lower().startswith("var("):
        index = value.find(literal)
        return value if index < 0 else value[:index] + replacement + value[index + len(literal):]
    if literal[0] in "#" or literal[0].isalpha():
        pattern = rf"(?<![\w#-]){re.escape(literal)}(?![\w-])"
    else:
        pattern = rf"(?<![\w.#-]){re.escape(literal)}(?![\w.%])"
    spans = protected_spans(value)
    for found in re.finditer(pattern, value):
        if not any(start <= found.start() < end for start, end in spans):
            return value[:found.start()] + replacement + value[found.end():]
    return value


def comment_removal(text, start, end):
    """Extend a comment's span over the spaces before it so the line stays tidy."""
    while start > 0 and text[start - 1] in " \t":
        start -= 1
    return start, end


def rewrite(project, system, choose):
    """Apply choose(item) -> (replacements, strip_comment) to every checked declaration.

    Returns a list of (relative file, line, before, after) changes and writes the files.
    """
    edits = defaultdict(list)
    texts = {}
    stripped = set()
    for item in scan(project, system):
        path = item.block.path
        if path not in texts:
            texts[path] = path.read_text(encoding="utf-8")
        replacements, strip = choose(item)
        if item.value_span and replacements:
            start = item.block.offset + item.value_span[0]
            end = item.block.offset + item.value_span[1]
            before = texts[path][start:end]
            after = before
            for literal, new in replacements:
                after = replace_once(after, literal, new)
            if after != before:
                edits[path].append((start, end, after, item.line, f"{item.prop}: {before}", f"{item.prop}: {after}"))
        if strip and item.comment_span and (path, item.block.offset + item.comment_span[0]) not in stripped:
            stripped.add((path, item.block.offset + item.comment_span[0]))
            start, end = comment_removal(texts[path], item.block.offset + item.comment_span[0],
                                         item.block.offset + item.comment_span[1])
            edits[path].append((start, end, "", item.line, texts[path][start:end].strip(), "(exception comment removed)"))

    changes = []
    for path, items in edits.items():
        text = texts[path]
        for start, end, new, line, before, after in sorted(items, key=lambda e: e[0], reverse=True):
            text = text[:start] + new + text[end:]
            changes.append((path.relative_to(project).as_posix(), line, before, after))
        path.write_text(text, encoding="utf-8")
    return sorted(changes)


def load_config(project):
    path = project / "portably.config.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"namespace": namespace_for(project)}


def save_config(project, config):
    (project / "portably.config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def format_tokens(node, indent=0):
    """tokens.json the way people read it: groups indented, each token on one line."""
    pad = "  " * (indent + 1)
    lines = []
    for key, value in node.items():
        name = json.dumps(key, ensure_ascii=False)
        if isinstance(value, dict) and "$value" not in value and not key.startswith("$"):
            lines.append(f"{pad}{name}: {format_tokens(value, indent + 1)}")
        else:
            lines.append(f"{pad}{name}: {json.dumps(value, ensure_ascii=False, separators=(',', ':'))}")
    return "{\n" + ",\n".join(lines) + "\n" + "  " * indent + "}"


def rebuild_tokens(project, source):
    namespace = namespace_for(project / "tokens")
    (project / "tokens/tokens.json").write_text(format_tokens(source) + "\n", encoding="utf-8")
    (project / "tokens/tokens.css").write_text(generate(source, namespace=namespace), encoding="utf-8")


def fix_project(path):
    """Make every safe fix. Returns a list of plain-language lines describing what changed."""
    project = find_project(path)
    done = []
    namespace = namespace_for(project / "tokens")

    for name, text in canonical_foundation(namespace).items():
        target = project / "foundation" / name
        if not target.is_file() or target.read_text(encoding="utf-8") != text:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            done.append(f"Restored foundation/{name} from Portably.")

    for name in HANDOFF_FILES:
        if not (project / name).is_file():
            (project / name).write_text(template(name, project, namespace), encoding="utf-8")
            done.append(f"Created {name} from the Portably template."
                        + (" Fill in the pages and known gaps before handoff." if name == "README.md" else ""))

    try:
        system, _ = load_system(project)
    except (ValueError, KeyError, json.JSONDecodeError):
        done.append("Skipped the design-system fixes: tokens.json can't be read yet (see the check below).")
        return done

    normalizations = []

    def choose(item):
        if item.exception and item.decision_keys:
            return [], False
        replacements = []
        for j in item.judgements:
            if j.replacement is None:
                continue
            replacements.append((j.literal, j.replacement))
            if j.kind == "snap":
                rel = item.block.path.relative_to(project).as_posix()
                normalizations.append(f"`{j.literal}` → `{j.token}` ({item.prop}, {rel})")
        return replacements, bool(item.exception)

    for rel, line, before, after in rewrite(project, system, choose):
        done.append(f"{rel}:{line}  {before}  →  {after}")

    if normalizations:
        config = load_config(project)
        recorded = config.setdefault("normalizations", [])
        for entry in normalizations:
            if entry not in recorded:
                recorded.append(entry)
        save_config(project, config)
    return done


# ---- promote -------------------------------------------------------------------------------------

KINDS = {"spacing": "space", "radius": "radius", "font-size": "font.size", "line-height": "font.line-height",
         "letter-spacing": "font.tracking", "shadow": "shadow", "colour": "color", "color": "color", "breakpoint": None}
KIND_LIST = "spacing, radius, font-size, line-height, letter-spacing, shadow, colour or breakpoint"


def parse_length(text):
    found = re.fullmatch(r"\s*(\d*\.?\d+)\s*(px|rem)?\s*", text, re.I)
    if not found:
        raise PromoteError(f"`{text}` isn't a size. Write it like 80px or 5rem.")
    number, unit = float(found.group(1)), (found.group(2) or "px").lower()
    return number * (ROOT_PX if unit == "rem" else 1)


def suggest_size(scale, px):
    """Suggest the next t-shirt size above or below an existing scale, or None when the value falls in between."""
    sized = {path.rsplit(".", 1)[1]: value for path, value in scale.items() if path.rsplit(".", 1)[1] in SIZE_NAMES}
    if not sized:
        return None
    largest = max(sized, key=sized.get)
    smallest = min(sized, key=sized.get)
    if px > sized[largest] and SIZE_NAMES.index(largest) + 1 < len(SIZE_NAMES):
        return SIZE_NAMES[SIZE_NAMES.index(largest) + 1]
    if px < sized[smallest] and SIZE_NAMES.index(smallest) > 0:
        return SIZE_NAMES[SIZE_NAMES.index(smallest) - 1]
    return None


def token_path(group, name):
    if name is None:
        return None
    name = name.strip()
    path = name if name.startswith(group + ".") else f"{group}.{name}"
    if not all(KEY.fullmatch(part) for part in path.split(".")):
        raise PromoteError(f"`{name}` can't be a token name. Use letters, numbers and hyphens, like {group}.card.")
    return path


def set_token(source, path, token):
    node = source
    parts = path.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
        if "$value" in node:
            raise PromoteError(f"`{path}` would sit inside the token `{part}`. Pick another name.")
    node[parts[-1]] = token
    return node


def sort_group(node, measure):
    keys = [k for k in node if k.startswith("$")]
    items = sorted((k for k in node if not k.startswith("$")), key=lambda k: measure(node[k]))
    ordered = {k: node[k] for k in keys + items}
    node.clear()
    node.update(ordered)


def dimension_px(token):
    value = token.get("$value")
    if isinstance(value, dict) and "value" in value:
        return value["value"] * (ROOT_PX if value.get("unit") == "rem" else 1)
    return float("inf")


def promote(path, kind, value, name=None):
    """Add a value to the design system and use it everywhere it appears. Returns lines describing the change."""
    project = find_project(path)
    kind = kind.lower()
    if kind not in KINDS:
        raise PromoteError(f"`{kind}` can't be promoted. Choose one of: {KIND_LIST}.")

    if kind == "breakpoint":
        px = parse_length(value)
        config = load_config(project)
        label = name or f"custom{fmt(px)}Px"
        existing = config.setdefault("breakpoints", {})
        if label in existing and existing[label] != px:
            raise PromoteError(f"The breakpoint `{label}` already exists ({fmt(existing[label])}px). Pick another name with --as.")
        existing[label] = int(px) if px == int(px) else px
        save_config(project, config)
        system, _ = load_system(project)
        changes = rewrite(project, system, lambda item: ([], bool(item.exception and not item.decision_keys)))
        return [f"Added the breakpoint {fmt(px)}px (`{label}`) to portably.config.json."] + \
               [f"{rel}:{line}  {before}  →  {after}" for rel, line, before, after in changes]

    source = json.loads((project / "tokens/tokens.json").read_text(encoding="utf-8"))
    system, _ = load_system(project)
    group = KINDS[kind]

    if kind == "spacing":
        px = parse_length(value)
        step = spacing_step_name(px)
        if not step:
            raise PromoteError(f"Spacing steps move in 2px, so {fmt(px)}px can't be one. "
                               f"Use {fmt(round(px / 2) * 2)}px instead (snap the CSS to it first).")
        path_ = token_path(group, name) or step
        if path_ != step:
            raise PromoteError(f"Spacing steps are named px ÷ 4, so {fmt(px)}px is `{step}`. Leave out --as.")
        token = {"$type": "dimension", "$value": {"value": px / ROOT_PX, "unit": "rem"}}
        shown = f"{fmt(px)}px"
    elif kind in ("radius", "font-size"):
        px = parse_length(value)
        scale = system.radius if kind == "radius" else system.font_size
        path_ = token_path(group, name)
        if not path_:
            size = suggest_size(scale, px)
            example = f"{group}.{size}" if size else f"{group}.card"
            raise PromoteError(f"Give the new {kind.replace('-', ' ')} a name with --as, for example: --as {example}")
        unit = "px" if kind == "radius" else "rem"
        token = {"$type": "dimension", "$value": {"value": px if unit == "px" else px / ROOT_PX, "unit": unit}}
        shown = f"{fmt(px)}px"
    elif kind == "line-height":
        try:
            number = float(value)
        except ValueError:
            raise PromoteError(f"`{value}` isn't a line height. Write it without a unit, like 1.3.") from None
        path_ = token_path(group, name)
        if not path_:
            raise PromoteError("Give the line height a name with --as, for example: --as font.line-height.card")
        token = {"$type": "number", "$value": number}
        shown = fmt(number)
    elif kind == "letter-spacing":
        found = re.fullmatch(r"\s*(-?\d*\.?\d+)\s*(px|rem|em)\s*", value, re.I)
        if not found:
            raise PromoteError(f"`{value}` isn't a letter spacing. Write it like 0.08em or -0.5px.")
        path_ = token_path(group, name)
        if not path_:
            raise PromoteError("Give the letter spacing a name with --as, for example: --as font.tracking.heading")
        number = float(found.group(1))
        token = {"$type": "dimension", "$value": {"value": int(number) if number == int(number) else number,
                                                  "unit": found.group(2).lower()}}
        shown = value.strip()
    elif kind == "shadow":
        parsed = parse_shadow(value)
        if not parsed:
            raise PromoteError(f"`{value}` isn't a single shadow Portably can read. Write it like \"0 4px 12px rgba(0, 0, 0, 0.1)\".")
        path_ = token_path(group, name)
        if not path_:
            raise PromoteError("Give the shadow a name with --as, for example: --as shadow.card")
        lengths, rgb, alpha, inset = parsed
        colour = to_hex(rgb) if alpha == 1 else f"rgb({' '.join(str(round(c)) for c in rgb)} / {fmt(round(alpha, 3))})"
        token = {"$type": "shadow", "$value": {"color": colour, **{
            k: {"value": v, "unit": "px"} for k, v in zip(("offsetX", "offsetY", "blur", "spread"), lengths)}}}
        if inset:
            token["$value"]["inset"] = True
        shown = value.strip()
    else:
        parsed = parse_color(value.strip())
        if not parsed:
            raise PromoteError(f"`{value}` isn't a colour. Write it like {FORMATS}.")
        rgb, alpha = parsed
        if alpha < 1:
            raise PromoteError("Only solid colours can join the palette. Promote the solid colour and use it with "
                               "color-mix(in srgb, var(--token) 50%, transparent) where it's see-through.")
        if not name:
            raise PromoteError("Give the colour a name with --as, for example: --as color.palette.brand-pink")
        path_ = name if name.startswith("color.") else f"color.palette.{name}"
        token_path("color", path_)
        token = {"$type": "color", "$value": to_hex(rgb)}
        shown = to_hex(rgb)

    if path_ in system.tokens:
        existing = system.resolve(path_)
        same = (token_rgba(existing["$value"])[0] == parse_color(token["$value"])[0] if token["$type"] == "color"
                else existing["$value"] == token["$value"])
        if not same:
            raise PromoteError(f"`{path_}` already exists with a different value. Pick another name with --as.")
        added = f"`{path_}` is already in the system"
    else:
        node = set_token(source, path_, token)
        if token["$type"] == "dimension" and kind != "letter-spacing":
            sort_group(node, dimension_px)
        elif token["$type"] == "number":
            sort_group(node, lambda t: t["$value"] if isinstance(t.get("$value"), (int, float)) else float("inf"))
        added = f"Added `{path_}` ({shown}) to tokens.json"
        rebuild_tokens(project, source)
        system, _ = load_system(project)

    nearby = []

    def choose(item):
        # Only the exact value is promoted. A value that is merely close stays as written: it is a
        # different decision, which check reports and fix snaps (and records) only when asked.
        replacements = [(j.literal, j.replacement) for j in item.judgements
                        if j.kind == "token-value" and j.replacement and j.token == path_]
        close = [j for j in item.judgements if j.kind == "snap" and j.token == path_]
        nearby.extend(f"`{j.literal}` ({item.block.path.relative_to(project).as_posix()}:{item.line})" for j in close)
        # Keep the exception while any other value on the line still needs it.
        return replacements, bool(item.exception) and not item.decision_keys and not close

    changes = rewrite(project, system, choose)
    uses = sum(1 for *_, after in changes if after != "(exception comment removed)")
    lines = [f"{added} and used it in {uses} place{'s' if uses != 1 else ''}."]
    lines += [f"{rel}:{line}  {before}  →  {after}" for rel, line, before, after in changes]
    if nearby:
        lines.append(f"Left {len(nearby)} close but different value{'s' if len(nearby) != 1 else ''} as written: "
                     f"{', '.join(nearby)}. `check` lists them so you can decide.")
    if kind in ("colour", "color") and path_.startswith("color.palette."):
        lines.append("If this colour plays a role (text, surface, border…), add a role in tokens.json that points at it.")
    return lines
