"""Export Portably's documented DTCG token subset to CSS.

This is an intentionally constrained exporter, not a general DTCG conformance
validator. Supported: structured sRGB colors, dimensions, font families and
weights, numbers, single shadows, typography composites, and whole-token
curly-brace aliases.
"""
from __future__ import annotations

import json
import re

from colors import token_rgba
from naming import default_namespace, validate_namespace

REF = re.compile(r"\{([A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*)\}\Z")
KEY = re.compile(r"[A-Za-z0-9_-]+\Z")
SUPPORTED = {"color", "dimension", "fontFamily", "fontWeight", "number", "shadow", "typography"}
TYPO_FIELDS = {
    "fontFamily": "fontFamily",
    "fontSize": "dimension",
    "fontWeight": "fontWeight",
    "letterSpacing": "dimension",
    "lineHeight": "number",
}


def collect(node, path=(), out=None):
    if out is None:
        out = {}
    if not isinstance(node, dict):
        raise ValueError(f"Expected a token/group object at {'.'.join(path) or 'root'}")
    for key, item in node.items():
        if key.startswith("$"):
            continue
        if not KEY.fullmatch(key):
            raise ValueError(f"Invalid token name segment: {key!r}")
        if not isinstance(item, dict):
            raise ValueError(f"Expected object: {'.'.join(path + (key,))}")
        target = path + (key,)
        if "$value" in item:
            if item.get("$type") not in SUPPORTED:
                raise ValueError(f"Unsupported/missing type: {'.'.join(target)}")
            out[".".join(target)] = item
        else:
            collect(item, target, out)
    return out


def reference(value):
    if not isinstance(value, str):
        return None
    found = REF.fullmatch(value)
    return found.group(1) if found else None


def css_name(path, namespace=None):
    namespace = validate_namespace(namespace or default_namespace())
    return f"--{namespace}-" + path.replace(".", "-")


def dimension(value):
    if not isinstance(value, dict) or set(value) != {"value", "unit"}:
        raise ValueError(f"Invalid dimension: {value!r}")
    if value["unit"] not in ("px", "rem", "em") or type(value["value"]) not in (int, float):
        raise ValueError(f"Invalid dimension unit/value: {value!r}")
    return f'{value["value"]:g}{value["unit"]}'


def color(value):
    """CSS for a colour token: a string is kept as written; a DTCG object becomes hex or rgba()."""
    rgb, alpha = token_rgba(value)
    if isinstance(value, str):
        return value.strip()
    hex_value = value.get("hex")
    if hex_value is not None:
        if not isinstance(hex_value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", hex_value):
            raise ValueError("Invalid hex")
        decoded = [int(hex_value[i:i + 2], 16) for i in (1, 3, 5)]
        if any(abs(a - b) > 0.0003 for a, b in zip(decoded, rgb)):
            raise ValueError("Hex does not match color components")
        if alpha == 1:
            return hex_value
    r, g, b = (round(n) for n in rgb)
    return f"rgba({r}, {g}, {b}, {alpha:g})"


def scalar(value, kind):
    if kind == "color":
        return color(value)
    if kind == "dimension":
        return dimension(value)
    if kind == "fontFamily":
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list) or not value or not all(isinstance(n, str) and n for n in value):
            raise ValueError("Invalid font family")
        return ", ".join(n if re.fullmatch(r"[A-Za-z0-9_-]+", n) else json.dumps(n) for n in value)
    if kind in ("fontWeight", "number"):
        if type(value) not in (int, float):
            raise ValueError(f"Invalid {kind}")
        return f"{value:g}"
    if kind == "shadow":
        if not isinstance(value, dict):
            raise ValueError("Invalid shadow")
        return " ".join(dimension(value[k]) for k in ("offsetX", "offsetY", "blur", "spread")) + " " + color(value["color"]) + (" inset" if value.get("inset") else "")
    raise ValueError(f"Unsupported scalar type: {kind}")


def token_dependencies(source):
    tokens = collect(source)
    graph = {path: set() for path in tokens}
    for path, token in tokens.items():
        value = token["$value"]
        target = reference(value)
        if target:
            graph[path].add(target)
        elif token["$type"] == "typography" and isinstance(value, dict):
            for item in value.values():
                target = reference(item)
                if target:
                    graph[path].add(target)
    return graph


def emitted_variables(source, namespace=None):
    tokens = collect(source)
    result = {}
    for path, token in tokens.items():
        if token["$type"] == "typography" and not reference(token["$value"]):
            for field in TYPO_FIELDS:
                suffix = re.sub(r"(?<!^)(?=[A-Z])", "-", field).lower()
                result[f"{css_name(path, namespace)}-{suffix}"] = path
        else:
            result[css_name(path, namespace)] = path
    return result


def generate(source, namespace=None):
    namespace = validate_namespace(namespace or default_namespace())
    tokens = collect(source)
    if not tokens:
        raise ValueError("Empty token source")
    aliases = {}

    def validate(path, visiting=()):
        if path not in tokens:
            raise ValueError(f"Unknown token alias: {path}")
        if path in visiting:
            raise ValueError("Circular token alias: " + " -> ".join(visiting + (path,)))
        token = tokens[path]
        value = token["$value"]
        target = reference(value)
        if target:
            if target not in tokens or tokens[target]["$type"] != token["$type"]:
                raise ValueError(f"Missing/mismatched token alias: {path} -> {target}")
            validate(target, visiting + (path,))
            aliases[path] = target
        elif token["$type"] == "typography":
            if not isinstance(value, dict) or set(value) != set(TYPO_FIELDS):
                raise ValueError(f"Invalid typography properties: {path}")
            for field, kind in TYPO_FIELDS.items():
                prop = value[field]
                prop_ref = reference(prop)
                if prop_ref:
                    if prop_ref not in tokens or tokens[prop_ref]["$type"] != kind:
                        raise ValueError(f"Invalid typography alias: {path}.{field}")
                    validate(prop_ref, visiting + (path,))
                else:
                    scalar(prop, kind)
        else:
            scalar(value, token["$type"])

    css_names = {}
    for path in tokens:
        name = css_name(path, namespace)
        if name in css_names:
            raise ValueError(f"CSS variable collision: {path} and {css_names[name]}")
        css_names[name] = path
        validate(path)

    output = [
        "/* Generated from tokens.json. Do not edit by hand. */",
        f"@layer {namespace}-tokens {{",
        f"  .{namespace} {{",
    ]
    for path, token in tokens.items():
        value, kind = token["$value"], token["$type"]
        if kind == "typography" and path not in aliases:
            for field, expected in TYPO_FIELDS.items():
                item = value[field]
                target = reference(item)
                rendered = f"var({css_name(target, namespace)})" if target else scalar(item, expected)
                suffix = re.sub(r"(?<!^)(?=[A-Z])", "-", field).lower()
                output.append(f"    {css_name(path, namespace)}-{suffix}: {rendered};")
            continue
        target = aliases.get(path)
        rendered = f"var({css_name(target, namespace)})" if target else scalar(value, kind)
        output.append(f"    {css_name(path, namespace)}: {rendered};")
    output.extend(["  }", "}", ""])
    return "\n".join(output)
