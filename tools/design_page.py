"""Write DESIGN-SYSTEM.html: the design system drawn with the project's own tokens, for people to look at.

It shows the same gathered data as DESIGN-SYSTEM.md (see design_doc.gather). Every swatch, type sample, spacing bar,
radius, shadow and button is drawn through the project's tokens.css, so the page always shows the live system.
"""
from __future__ import annotations

import json
import re
from html import escape

from build_tokens import css_name, reference
from check_system import fmt
from colors import contrast, over
from naming import HOME_URL, portably_version

PAGE_FILENAME = "DESIGN-SYSTEM.html"
TYPO_SUFFIXES = ("font-family", "font-size", "font-weight", "line-height", "letter-spacing")


def code(text):
    """A token path or file name as <code>, allowed to wrap after each dot or slash on a narrow screen."""
    return "<code>" + re.sub(r"([./])", r"\1<wbr>", escape(str(text), quote=False)) + "</code>"


def inline(text):
    """Escape plain text and turn `code` spans into <code>."""
    parts = str(text).split("`")
    if len(parts) % 2 == 0:  # an unmatched backtick: show the text as it is
        return escape(str(text), quote=False)
    return "".join(code(part) if i % 2 else escape(part, quote=False) for i, part in enumerate(parts))


def table(head, rows):
    if not rows:
        return '<p class="ds-none">None.</p>'
    cells = "".join(f"<th scope=\"col\">{escape(h)}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<div class="ds-table"><table><thead><tr>{cells}</tr></thead><tbody>{body}</tbody></table></div>'


def items(values):
    if not values:
        return '<p class="ds-none">None.</p>'
    return "<ul>" + "".join(f"<li>{inline(v)}</li>" for v in values) + "</ul>"


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def section(anchor, title, intro, body):
    intro = f'<p class="ds-intro">{intro}</p>' if intro else ""
    body = re.sub(r"<h3>(.*?)</h3>", lambda m: f'<h3 id="{anchor}-{slug(m.group(1))}">{m.group(1)}</h3>', body)
    return f'<section class="ds-section" id="{anchor}"><h2>{escape(title)}</h2>{intro}{body}</section>'


# The sidebar's name for each section; the parts inside a section are listed under it.
SECTION_NAMES = {"context": "Source", "colours": "Colours", "type": "Typography", "spacing": "Spacing",
                 "shape": "Radius and shadows", "button": "Button", "layout": "Layout", "decisions": "Decisions",
                 "structure": "Pages and components"}


def sidebar(parts):
    groups = []
    for part in parts:
        anchor = re.match(r'<section class="ds-section" id="([\w-]+)"', part).group(1)
        inner = "".join(f'<li><a class="ds-sidebar-link ds-sidebar-link--sub" href="#{sub}">{label}</a></li>'
                        for sub, label in re.findall(r'<h3 id="([\w-]+)">(.*?)</h3>', part))
        inner = f'<ul class="ds-sidebar-list ds-sidebar-list--sub">{inner}</ul>' if inner else ""
        groups.append(f'<li><a class="ds-sidebar-link" href="#{anchor}" data-js="ds-section-link">'
                      f'{escape(SECTION_NAMES.get(anchor, anchor))}</a>{inner}</li>')
    return f'<ul class="ds-sidebar-list">{"".join(groups)}</ul>'


def style_block(ns):
    v = lambda path: f"var({css_name(path, ns)})"  # noqa: E731
    heading = lambda path: "; ".join(f"{s}: var({css_name(path, ns)}-{s})" for s in TYPO_SUFFIXES)  # noqa: E731
    return f"""
    .{ns} .ds-header {{ position: sticky; top: 0; z-index: 2; border-bottom: 1px solid {v('color.border.default')}; background: {v('color.background')}; }}
    .{ns} .ds-header-inner, .{ns} .ds-layout {{ max-width: {v('layout.wrapper.max')}; margin-inline: auto; padding-inline: {v('layout.wrapper.gutter')}; }}
    .{ns} .ds-header-inner {{ display: flex; align-items: center; justify-content: space-between; gap: {v('space.4')}; block-size: 4rem; }}
    .{ns} .ds-where {{ min-width: 0; margin: 0; overflow: hidden; color: {v('color.text.muted')}; font-size: {v('font.size.sm')}; text-overflow: ellipsis; white-space: nowrap; }}
    .{ns} .ds-where strong {{ color: {v('color.text.primary')}; font-weight: {v('font.weight.medium')}; }}
    .{ns} .ds-actions {{ display: flex; gap: {v('space.2')}; }}
    .{ns} .ds-sidebar, .{ns} .ds-table {{ scrollbar-width: thin; scrollbar-color: {v('color.text.soft')} transparent; }}
    .ds-embedded .{ns} .ds-sidebar, .ds-embedded .{ns} .ds-table {{ scrollbar-width: none; }}
    .{ns} .ds-icon-button {{ display: inline-grid; place-items: center; inline-size: 2.5rem; block-size: 2.5rem; padding: 0; border: 1px solid {v('color.border.default')}; border-radius: {v('radius.md')}; background: none; color: {v('color.text.primary')}; cursor: pointer; }}
    .{ns} .ds-icon-button:hover {{ border-color: {v('color.text.muted')}; }}
    .{ns} .ds-icon-button svg {{ inline-size: 1.25rem; block-size: 1.25rem; }}
    .{ns} .ds-theme-icon--other, .{ns} [aria-pressed="true"] .ds-theme-icon--default {{ display: none; }}
    .{ns} [aria-pressed="true"] .ds-theme-icon--other {{ display: block; }}
    .{ns} .ds-sidebar-list {{ display: grid; gap: {v('space.1')}; margin: 0; padding: 0; list-style: none; }}
    .{ns} .ds-sidebar-list--sub {{ margin-block: {v('space.1')} {v('space.2')}; padding-left: {v('space.3')}; border-left: 1px solid {v('color.border.default')}; }}
    .{ns} .ds-sidebar-link {{ display: block; padding-block: {v('space.1')}; color: {v('color.text.muted')}; font-weight: {v('font.weight.medium')}; text-decoration: none; }}
    .{ns} .ds-sidebar-link--sub {{ font-size: {v('font.size.sm')}; font-weight: {v('font.weight.regular')}; }}
    .{ns} .ds-sidebar-link:hover, .{ns} .ds-sidebar-link[aria-current="true"] {{ color: {v('color.text.primary')}; }}
    .{ns} .ds-sidebar-link[aria-current="true"] {{ font-weight: {v('font.weight.semibold')}; }}
    .{ns} .ds {{ min-width: 0; padding-block: {v('space.10')}; }}
    .{ns} .ds-section, .{ns} .ds h3 {{ scroll-margin-top: 5rem; }}
    @media (min-width: 60rem) {{
      .{ns} .ds-layout {{ display: grid; grid-template-columns: 14rem minmax(0, 1fr); gap: {v('space.10')}; }}
      .{ns} .ds-sidebar {{ position: sticky; top: 4rem; align-self: start; max-block-size: calc(100vh - 4rem); overflow-y: auto; padding-block: {v('space.10')}; }}
      .{ns} .ds-menu {{ display: none; }}
      .ds-embedded .{ns} .ds-header {{ display: none; }}
      .ds-embedded .{ns} .ds-sidebar {{ top: 0; max-block-size: 100vh; }}
    }}
    .ds-embedded .{ns} [data-js="ds-theme"] {{ display: none; }}
    @media (max-width: 59.99rem) {{
      .{ns} .ds-sidebar {{ padding-block: {v('space.6')}; border-bottom: 1px solid {v('color.border.default')}; }}
      .{ns} .ds-sidebar[data-open="false"] {{ display: none; }}
      .{ns} .ds-sidebar[data-open="true"] {{ position: fixed; inset: 4rem 0 0; z-index: 1; overflow-y: auto; padding: {v('space.6')} {v('layout.wrapper.gutter')}; background: {v('color.background')}; }}
    }}
    .{ns} .ds h1 {{ {heading('text.heading.lg')}; font-size: clamp({v('font.size.2xl')}, 8vw, var({css_name('text.heading.lg', ns)}-font-size)); margin-block: {v('space.2')} {v('space.4')}; }}
    .{ns} .ds h2 {{ {heading('text.heading.md')}; margin-bottom: {v('space.3')}; }}
    .{ns} .ds h3 {{ {heading('text.label.sm')}; margin-block: {v('space.6')} {v('space.3')}; color: {v('color.text.muted')}; text-transform: uppercase; }}
    .{ns} .ds-eyebrow, .{ns} .ds-meta, .{ns} .ds-intro, .{ns} .ds-none {{ color: {v('color.text.muted')}; }}
    .{ns} .ds-eyebrow {{ {heading('text.label.sm')}; text-transform: uppercase; }}
    .{ns} .ds-intro {{ max-width: {v('layout.measure.normal')}; margin-bottom: {v('space.4')}; }}
    .{ns} .ds a {{ color: {v('color.text.primary')}; }}
    .{ns} .ds a:hover {{ color: {v('color.action.hover')}; }}
    .{ns} .ds-footer {{ margin-top: {v('space.10')}; padding-top: {v('space.6')}; border-top: 1px solid {v('color.border.default')}; color: {v('color.text.muted')}; font-size: {v('font.size.sm')}; }}
    .{ns} .ds-hidden {{ position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }}
    .{ns} .ds-section {{ padding-block: {v('space.10')}; border-top: 1px solid {v('color.border.default')}; }}
    .{ns} .ds ul {{ display: grid; gap: {v('space.2')}; padding-left: {v('space.6')}; }}
    .{ns} .ds code {{ font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 0.9em; }}
    .{ns} .ds-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(9rem, 1fr)); gap: {v('space.6')}; }}
    .{ns} .ds-chip {{ block-size: 4rem; margin-bottom: {v('space.2')}; border: 1px solid {v('color.border.default')}; border-radius: {v('radius.md')}; }}
    .{ns} .ds-meta {{ font-size: {v('font.size.sm')}; overflow-wrap: break-word; }}
    .{ns} .ds-meta strong {{ display: block; color: {v('color.text.primary')}; }}
    .{ns} .ds-rows {{ display: grid; gap: {v('space.4')}; }}
    .{ns} .ds-row {{ display: grid; grid-template-columns: minmax(0, 1fr); gap: {v('space.1')}; }}
    .{ns} .ds-sample {{ overflow-wrap: break-word; }}
    .{ns} .ds-bar {{ block-size: {v('space.3')}; background: {v('color.action.primary')}; border-radius: {v('radius.sm')}; }}
    .{ns} .ds-shape {{ block-size: 5rem; border: 1px solid {v('color.border.default')}; background: {v('color.surface.raised')}; margin-bottom: {v('space.2')}; }}
    .{ns} .ds-pair {{ display: inline-block; padding: {v('space.1')} {v('space.3')}; border: 1px solid {v('color.border.default')}; border-radius: {v('radius.sm')}; font-size: {v('font.size.2xl')}; font-weight: {v('font.weight.bold')}; }}
    .{ns} .ds-buttons {{ display: flex; flex-wrap: wrap; gap: {v('space.4')}; margin-bottom: {v('space.4')}; }}
    .{ns} .ds-table {{ overflow-x: auto; }}
    .{ns} .ds table {{ width: 100%; border-collapse: collapse; font-size: {v('font.size.sm')}; }}
    .{ns} .ds th, .{ns} .ds td {{ padding: {v('space.2')} {v('space.3')}; border-bottom: 1px solid {v('color.border.default')}; text-align: left; vertical-align: top; }}
    .{ns} .ds th {{ color: {v('color.text.muted')}; font-weight: {v('font.weight.semibold')}; }}
    @media (min-width: 40rem) {{ .{ns} .ds-row {{ grid-template-columns: 12rem minmax(0, 1fr); align-items: baseline; }} }}
"""


def theme_toggle(g):
    """The default theme ("light" or "dark", from its background) and the project's opposite theme, if it has one."""
    rgb, alpha = g.system.colors.get("color.background", ((255, 255, 255), 1))
    background = over(rgb, alpha, (255, 255, 255))
    default = "dark" if contrast(background, (255, 255, 255)) > contrast(background, (0, 0, 0)) else "light"
    other = "light" if default == "dark" else "dark"
    for theme in g.themes:
        name = theme.get("value") or re.sub(r"^data-", "", theme.get("name", ""))
        if theme["kind"] != "scheme" and name.lower() == other:
            return default, {"slug": other, **{k: theme.get(k) or "" for k in ("kind", "target", "name", "value")}}
    return default, None


ICONS = {
    "dark": '<path d="M20.5 13.5A8.5 8.5 0 1 1 10.5 3.5a6.5 6.5 0 0 0 10 10z"/>',
    "light": '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M2.5 12h2M19.5 12h2M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
}


def icon(name, cls=""):
    extra = f' class="{cls}"' if cls else ""
    return (f'<svg{extra} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true" focusable="false">{ICONS[name]}</svg>')


PAGE_SCRIPT = """
  <script>
    (() => {
      // Theme: the page opens in the theme named in its address (?theme=).
      const other = %s;
      const fallback = %s;
      const toggle = document.querySelector('[data-js="ds-theme"]');
      const setTheme = (asked) => {
        const on = Boolean(other) && asked === other.slug;
        if (other) {
          const element = other.target === 'body' ? document.body : document.documentElement;
          if (other.kind === 'class') element.classList.toggle(other.name, on);
          else if (on) element.setAttribute(other.name, other.value);
          else element.removeAttribute(other.name);
          toggle.setAttribute('aria-pressed', String(on));
        }
        return on ? other.slug : fallback;
      };
      if (toggle) toggle.addEventListener('click', () => {
        const next = setTheme(toggle.getAttribute('aria-pressed') === 'true' ? fallback : other.slug);
        history.replaceState(null, '', `?theme=${next}${location.hash}`);
      });
      setTheme(new URLSearchParams(location.search).get('theme'));

      // The list of sections: a menu on small screens.
      const menu = document.querySelector('[data-js="ds-menu"]');
      const sidebar = document.getElementById('ds-sidebar');
      const setOpen = (open) => {
        menu.setAttribute('aria-expanded', String(open));
        sidebar.dataset.open = String(open);
      };
      menu.hidden = false;
      setOpen(false);
      menu.addEventListener('click', () => setOpen(menu.getAttribute('aria-expanded') !== 'true'));
      sidebar.addEventListener('click', (event) => { if (event.target.closest('a')) setOpen(false); });
      document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && menu.getAttribute('aria-expanded') === 'true') { setOpen(false); menu.focus(); }
      });

      // Mark the section being read.
      const links = [...document.querySelectorAll('[data-js="ds-section-link"]')];
      const where = document.querySelector('[data-js="ds-where"]');
      const embedded = document.documentElement.classList.contains('ds-embedded');
      if (!('IntersectionObserver' in window)) return;
      const visible = new Set();
      const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => (entry.isIntersecting ? visible.add(entry.target.id) : visible.delete(entry.target.id)));
        const current = links.find((link) => visible.has(link.hash.slice(1)));
        if (!current) return;
        links.forEach((link) => link.removeAttribute('aria-current'));
        current.setAttribute('aria-current', 'true');
        if (embedded && where) where.textContent = current.textContent;
      }, { rootMargin: '-64px 0px -60%% 0px' });
      links.forEach((link) => { const target = document.getElementById(link.hash.slice(1)); if (target) observer.observe(target); });
    })();
  </script>"""


def contrast_rows(g, var):
    from check import CONTRAST_PAIRS  # imported here: check imports this module's caller
    colours, rows = g.system.colors, []
    for fg, bg, need, purpose in CONTRAST_PAIRS:
        if fg not in colours or bg not in colours:
            continue
        (bg_rgb, bg_alpha), (fg_rgb, fg_alpha) = colours[bg], colours[fg]
        base = over(bg_rgb, bg_alpha, (255, 255, 255))
        ratio = contrast(over(fg_rgb, fg_alpha, base), base)
        verdict = "passes" if ratio >= need - 0.005 else "too low"
        sample = f'<span class="ds-pair" style="color: {var(fg)}; background: {var(bg)}">Aa</span>'
        rows.append((sample, f"{code(fg)} on {code(bg)}", escape(purpose), f"{ratio:.1f}:1", f"{need:g}:1 · {verdict}"))
    return rows


def render_page(g):
    """DESIGN-SYSTEM.html from the data gathered by design_doc.gather."""
    ns, d = g.namespace, g.d
    tokens = g.system.tokens

    def var(path, suffix=""):
        return f"var({css_name(path, ns)}{suffix})"

    def meta(path, value=None, note=True):
        added = " · added" if path in g.added else ""
        text = f'<p class="ds-meta"><strong>{code(path)}</strong>{inline(value if value is not None else d.value(path))}{added}'
        if note and d.note(path):
            text += f"<br>{inline(d.note(path))}"
        return text + "</p>"

    def swatches(paths):
        return '<div class="ds-grid">' + "".join(
            f'<div><div class="ds-chip" style="background: {var(p)}"></div>{meta(p, d.shown(p))}</div>' for p in paths) + "</div>"

    def typography(path):
        return "; ".join(f"{s}: {var(path, '-' + s)}" for s in TYPO_SUFFIXES)

    def row(path, style, sample, value=None):
        return (f'<div class="ds-row">{meta(path, value)}'
                f'<p class="ds-sample" style="{style}">{escape(sample)}</p></div>')

    parts = []
    source = " ".join(g.source) if g.source else "Not recorded yet: add \"source\" to portably.config.json."
    parts.append(section("context", "Where this design came from", None,
                         f"<p>{inline(source)}</p><h3>Assumptions</h3>{items(g.assumptions)}"
                         f"<h3>Deviations from the source</h3>{items(g.deviations)}"))

    parts.append(section("colours", "Colours", "Roles are what the CSS uses; each points at a palette colour.",
                         f"<h3>Roles</h3>{swatches(g.roles)}<h3>Palette</h3>{swatches(g.palette)}"
                         "<h3>Contrast</h3>"
                         + table(("Sample", "Pair", "Used for", "Ratio", "Needs"), contrast_rows(g, var))))

    # A text style that aliases another has no CSS variables of its own; its target is drawn instead.
    text_rows = "".join(row(p, typography(p), "The quick brown fox jumps over the lazy dog") for p in g.text_styles
                        if tokens[p]["$type"] == "typography" and not reference(tokens[p]["$value"]))
    sizes = "".join(row(p, f"font-size: {var(p)}; line-height: 1.1", "Aa") for p in g.sizes)
    weights = "".join(row(p, f"font-weight: {var(p)}", "The quick brown fox") for p in g.weights)
    tracking = "".join(row(p, f"letter-spacing: {var(p)}", "Letter spacing") for p in g.tracking)
    families = "".join(row(p, f"font-family: {var(p)}", "The quick brown fox jumps over the lazy dog") for p in g.families)
    line_heights = table(("Token", "Value"), [(code(p), inline(d.value(p))) for p in g.line_heights])
    parts.append(section("type", "Typography", None,
                         f'<h3>Text styles</h3><div class="ds-rows">{text_rows}</div>'
                         f'<h3>Fonts</h3><div class="ds-rows">{families}</div>'
                         f'<h3>Sizes</h3><div class="ds-rows">{sizes}</div>'
                         f'<h3>Weights</h3><div class="ds-rows">{weights}</div>'
                         f'<h3>Letter spacing</h3><div class="ds-rows">{tracking}</div>'
                         f"<h3>Line heights</h3>{line_heights}"))

    bars = "".join(f'<div class="ds-row">{meta(p)}<div class="ds-bar" style="inline-size: {var(p)}"></div></div>' for p in g.spacing)
    parts.append(section("spacing", "Spacing", "Steps on a 4px grid.", f'<div class="ds-rows">{bars}</div>'))

    radii = "".join(f'<div><div class="ds-shape" style="border-radius: {var(p)}"></div>{meta(p)}</div>' for p in g.radii)
    shadows = "".join(f'<div><div class="ds-shape" style="box-shadow: {var(p)}"></div>{meta(p)}</div>' for p in g.shadows)
    parts.append(section("shape", "Radius and shadows", None,
                         f'<h3>Radius</h3><div class="ds-grid">{radii}</div><h3>Shadows</h3><div class="ds-grid">{shadows}</div>'))

    buttons = (f'<div class="ds-buttons"><button class="{ns}-btn {ns}-btn--primary" type="button">Primary</button>'
               f'<button class="{ns}-btn {ns}-btn--secondary" type="button">Secondary</button>'
               f'<button class="{ns}-btn {ns}-btn--primary" type="button" disabled>Disabled</button></div>')
    parts.append(section("button", "Button", f"<code>{ns}-btn</code> takes its shape from these tokens and its colours from the action roles.",
                         buttons + table(("Token", "Value"), [(code(p), inline(d.shown(p))) for p in g.button])))

    layout = table(("Token", "Value", "Notes"), [(code(p), inline(d.shown(p)), inline(d.note(p))) for p in g.layout])
    breakpoints = table(("Breakpoint", "Width"), [(escape(name), f"{fmt(px)}px") for name, px in g.breakpoints])
    parts.append(section("layout", "Layout and breakpoints", None, layout + "<h3>Breakpoints</h3>" + breakpoints))

    changed = table(("Token", "Portably default", "This project", "Notes"),
                    [(code(p), inline(g.base.shown(p)), inline(d.shown(p)), inline(d.note(p))) for p in g.changed])
    added = table(("Token", "Value", "Notes"), [(code(p), inline(d.shown(p)), inline(d.note(p))) for p in g.added])
    exceptions = table(("Where", "Value", "Reason"),
                       [(code(f"{e.file}:{e.line}"), code(e.snippet), inline(e.reason))
                        for e in g.exceptions])
    parts.append(section("decisions", "What this project decided", "Portably starts every project from a complete default system.",
                         f"<h3>Changed from the Portably defaults</h3>{changed}<h3>Added for this project</h3>{added}"
                         f"<h3>Normalizations</h3>{items(g.normalizations)}"
                         f"<h3>Changed for readability</h3>{items(g.readability)}"
                         f"<h3>Exceptions</h3>{exceptions}"))

    def page_link(rel, title=""):
        return f'<a href="{escape(rel)}">{escape(title or rel)}</a>'

    pages = items([]) if not g.pages else "<ul>" + "".join(
        f"<li>{page_link(rel, title)} {code(rel)}</li>" for rel, title in g.pages) + "</ul>"
    sheets = table(("Stylesheet", "Classes", "Used on"),
                   [(code(rel), " ".join(code(b) for b in blocks) or "none",
                     ", ".join(page_link(u) for u in used) or "no page yet") for rel, blocks, used in g.sheets])
    parts.append(section("structure", "Pages and components",
                         "Each component and page stylesheet, the classes it styles and the pages that use them.",
                         f"<h3>Pages</h3>{pages}<h3>Stylesheets</h3>{sheets}"))

    title = escape(g.title)
    default, other = theme_toggle(g)
    scheme = ":root { color-scheme: dark; }\n    " if default == "dark" else ""
    project_css = "\n    ".join([*g.font_faces, *g.theme_css])
    toggle = ""
    if other:
        toggle = (f'<button class="ds-icon-button" type="button" data-js="ds-theme" aria-label="{other["slug"].capitalize()} theme" '
                  f'aria-pressed="false">{icon(default, "ds-theme-icon--default")}{icon(other["slug"], "ds-theme-icon--other")}</button>')
    where = f'<p class="ds-where" data-js="ds-where"><strong>{title}</strong> · Design system</p>'
    menu = (f'<button class="ds-icon-button ds-menu" type="button" data-js="ds-menu" aria-controls="ds-sidebar" '
            f'aria-expanded="false" aria-label="Sections" hidden>{icon("menu")}</button>')
    script = PAGE_SCRIPT % (json.dumps(other), json.dumps(default))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="generator" content="Portably {portably_version()}">
  <title>Design system · {title}</title>
  <script>if (new URLSearchParams(location.search).has('embed')) document.documentElement.classList.add('ds-embedded');</script>
  <link rel="stylesheet" href="foundation/system.css">
  <link rel="stylesheet" href="tokens/tokens.css">
  <style>
    {scheme}{project_css}{style_block(ns)}  </style>
</head>
<body class="{ns}">
  <!-- Generated by Portably from tokens/tokens.json and portably.config.json. Don't edit: run portably check. -->
  <header class="ds-header">
    <div class="ds-header-inner">{where}<div class="ds-actions">{toggle}{menu}</div></div>
  </header>
  <div class="ds-layout">
    <nav class="ds-sidebar" id="ds-sidebar" aria-label="Design system">{sidebar(parts)}</nav>
    <main class="ds">
      <header>
        <p class="ds-eyebrow">Design system</p>
        <h1>{title}</h1>
        <p class="ds-intro">Generated by Portably from <code>tokens/tokens.json</code> and <code>portably.config.json</code>. Everything here is drawn with the project's own tokens; <code>DESIGN-SYSTEM.md</code> has the same content as text.</p>
      </header>
      {chr(10).join(parts)}
      <footer class="ds-footer">
        <p>Generated by <a href="{HOME_URL}" target="_blank" rel="noopener">Portably {portably_version()}<span class="ds-hidden"> (opens in a new tab)</span></a></p>
      </footer>
    </main>
  </div>{script}
</body>
</html>
"""
