"""Colour parsing and contrast, shared by the token exporter, the checks and promote.

A colour can be written the way designers copy it: #2F6B4F, rgb(47 107 79), hsl(152 39% 30%),
oklch(0.47 0.07 160) or oklab(…). Everything is compared in sRGB.
"""
from __future__ import annotations

import colorsys
import math
import re

HEX = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b")
COLOR_FUNC = re.compile(r"\b(rgba?|hsla?|oklch|oklab)\(([^()]*)\)", re.I)
FORMATS = "#2F6B4F, rgb(47 107 79), hsl(152 39% 30%) or oklch(0.47 0.07 160)"


def _number(text, percent_scale):
    text = text.strip().lower()
    if text == "none":
        return 0.0
    if text.endswith("%"):
        return float(text[:-1]) * percent_scale / 100
    return float(re.sub(r"deg\Z", "", text))


def _gamma(channel):
    channel = max(0.0, min(1.0, channel))
    return 12.92 * channel if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055


def _oklab_to_rgb(lightness, a, b):
    l_ = lightness + 0.3963377774 * a + 0.2158037573 * b
    m_ = lightness - 0.1055613458 * a - 0.0638541728 * b
    s_ = lightness - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    linear = (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
              -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
              -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)
    return tuple(_gamma(c) * 255 for c in linear)


def parse_color(literal):
    """Return ((r, g, b) 0–255, alpha 0–1) for a CSS colour, or None if it isn't one Portably reads."""
    literal = literal.strip()
    if HEX.fullmatch(literal):
        digits = literal[1:]
        if len(digits) in (3, 4):
            digits = "".join(c * 2 for c in digits)
        rgb = tuple(float(int(digits[i:i + 2], 16)) for i in (0, 2, 4))
        alpha = int(digits[6:8], 16) / 255 if len(digits) == 8 else 1.0
        return rgb, round(alpha, 3)
    found = COLOR_FUNC.fullmatch(literal)
    if not found:
        return None
    name, args = found.group(1).lower(), found.group(2)
    body, _, alpha_text = args.partition("/")
    parts = [p for p in re.split(r"[\s,]+", body.strip()) if p]
    if len(parts) == 4 and not alpha_text:
        alpha_text = parts.pop()
    if len(parts) != 3:
        return None
    try:
        alpha = _number(alpha_text, 1) if alpha_text.strip() else 1.0
        if name.startswith("rgb"):
            rgb = tuple(_number(p, 255) for p in parts)
        elif name.startswith("hsl"):
            hue = _number(parts[0], 1) / 360
            r, g, b = colorsys.hls_to_rgb(hue % 1, _number(parts[2], 1), _number(parts[1], 1))
            rgb = (r * 255, g * 255, b * 255)
        elif name == "oklch":
            lightness, chroma, hue = _number(parts[0], 1), _number(parts[1], 0.4), _number(parts[2], 1)
            rgb = _oklab_to_rgb(lightness, chroma * math.cos(math.radians(hue)), chroma * math.sin(math.radians(hue)))
        else:
            rgb = _oklab_to_rgb(_number(parts[0], 1), _number(parts[1], 0.4), _number(parts[2], 0.4))
    except ValueError:
        return None
    rgb = tuple(max(0.0, min(255.0, c)) for c in rgb)
    return rgb, round(max(0.0, min(1.0, alpha)), 3)


def token_rgba(value):
    """The sRGB colour of a colour token's $value, written as a string or as a DTCG object."""
    if isinstance(value, str):
        parsed = parse_color(value)
        if parsed is None:
            raise ValueError(f"`{value}` isn't a colour Portably can read. Write it like {FORMATS}")
        return parsed
    if not isinstance(value, dict) or value.get("colorSpace") != "srgb":
        raise ValueError(f"Colours must be written like {FORMATS}")
    channels = value.get("components")
    if not isinstance(channels, list) or len(channels) != 3 or any(
            type(c) not in (int, float) or not 0 <= c <= 1 for c in channels):
        raise ValueError("Invalid sRGB channels")
    alpha = value.get("alpha", 1)
    if type(alpha) not in (int, float) or not 0 <= alpha <= 1:
        raise ValueError("Invalid alpha")
    return tuple(c * 255 for c in channels), float(alpha)


def to_hex(rgb):
    return "#" + "".join(f"{round(c):02X}" for c in rgb)


def luminance(rgb):
    def linear(channel):
        channel /= 255
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def over(top, alpha, bottom):
    """A translucent colour laid over an opaque one."""
    return tuple(t * alpha + b * (1 - alpha) for t, b in zip(top, bottom))


def contrast(a, b):
    """WCAG contrast ratio between two opaque sRGB colours (1 to 21)."""
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _rgb_to_oklab(rgb):
    def linear(channel):
        channel /= 255
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in rgb)
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def chroma(rgb):
    _, a, b = _rgb_to_oklab(rgb)
    return math.hypot(a, b)


def passing_shade(rgb, other, need):
    """The closest shade of rgb (same hue, lighter or darker) that has `need` contrast with `other`, or None."""
    lightness, a, b = _rgb_to_oklab(rgb)
    best = None
    for direction in (-1, 1):
        step = 0
        while True:
            step += 1
            target = lightness + direction * step * 0.005
            if not 0 <= target <= 1:
                break
            candidate = tuple(round(c) for c in _oklab_to_rgb(target, a, b))
            if contrast(candidate, other) >= need:
                if best is None or step < best[0]:
                    best = (step, candidate)
                break
    return to_hex(best[1]) if best else None
