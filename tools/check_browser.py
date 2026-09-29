"""Rendered checks for a Portably project, run when Playwright is installed."""
from __future__ import annotations

import base64
import os
import re
from pathlib import Path

from check_system import html_pages
from colors import passing_shade, to_hex
from naming import namespace_for
from report import Issue
from themes import project_themes

WIDTHS = (390, 1440)

# Finds every piece of visible text, and text that runs past the edge of the screen.
# The text is measured later against a picture of the page taken with all text hidden, so photos, gradients and
# overlays behind it count just like solid colours.
COLLECT_SCRIPT = """(width) => {
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 1;
  const ctx = canvas.getContext('2d', {willReadFrequently: true});
  const rgba = (colour) => {
    ctx.clearRect(0, 0, 1, 1);
    ctx.fillStyle = '#000';
    ctx.fillStyle = colour;
    ctx.fillRect(0, 0, 1, 1);
    const d = ctx.getImageData(0, 0, 1, 1).data;
    return [d[0], d[1], d[2], d[3] / 255];
  };
  const moving = new Set(document.getAnimations().map(a => a.effect && a.effect.target).filter(Boolean));
  const excused = (el) => {
    for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
      if (node.getAttribute('aria-hidden') === 'true' || moving.has(node)) return true;
      if (['auto', 'scroll'].includes(getComputedStyle(node).overflowX) && node !== document.documentElement && node !== document.body) return true;
    }
    return false;
  };
  // Only the part of the text its scrolling or clipping boxes show is on screen.
  const clipBox = (el) => {
    let [l, t, r, b] = [-Infinity, -Infinity, Infinity, Infinity];
    for (let node = el; node && node !== document.body && node !== document.documentElement; node = node.parentElement) {
      const s = getComputedStyle(node);
      if (s.overflowX !== 'visible' || s.overflowY !== 'visible') {
        const c = node.getBoundingClientRect();
        [l, t, r, b] = [Math.max(l, c.left), Math.max(t, c.top), Math.min(r, c.right), Math.min(b, c.bottom)];
      }
      if (s.position === 'fixed') break;
    }
    return [l, t, r, b];
  };
  const name = (el) => el.tagName.toLowerCase() +
    (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\\s+/).join('.') : '');
  const items = [], clipped = [];
  for (const el of document.body.querySelectorAll('*')) {
    if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE'].includes(el.tagName)) continue;
    const nodes = [...el.childNodes].filter(n => n.nodeType === 3 && n.textContent.trim());
    if (!nodes.length) continue;
    const text = nodes.map(n => n.textContent).join(' ').replace(/\\s+/g, ' ').trim();
    const style = getComputedStyle(el);
    const box = el.getBoundingClientRect();
    let seen = 1;
    for (let node = el; node && node.nodeType === 1; node = node.parentElement) seen *= parseFloat(getComputedStyle(node).opacity);
    if (style.visibility === 'hidden' || seen < 0.1 || box.width <= 1 || box.height <= 1) continue;
    const rects = [];
    for (const node of nodes) {
      const range = document.createRange();
      range.selectNodeContents(node);
      for (const r of range.getClientRects()) if (r.width >= 1 && r.height >= 1) rects.push(r);
    }
    if (!rects.length) continue;
    const short = text.length > 40 ? text.slice(0, 39) + '…' : text;
    if (rects.some(r => (r.left < width - 1 && r.right > width + 1) || (r.left < -1 && r.right > 1)) && !excused(el)) {
      clipped.push({selector: name(el), text: short});
    }
    const [cl, ct, cr, cb] = clipBox(el);
    const shown = rects.map(r => {
      const left = Math.max(r.left, cl), top = Math.max(r.top, ct);
      return [left, top, Math.min(r.right, cr) - left, Math.min(r.bottom, cb) - top];
    }).filter(([, , w, h]) => w >= 1 && h >= 1);
    if (!shown.length) continue;
    const fg = rgba(style.color), fill = rgba(style.webkitTextFillColor || style.color);
    if (fg[3] === 0 || fill[3] === 0 || el.closest(':disabled, [aria-disabled="true"]')) continue;
    const size = parseFloat(style.fontSize);
    const weight = parseInt(style.fontWeight, 10) || 400;
    const x = window.scrollX, y = window.scrollY;
    let pinned = false;
    for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
      if (['fixed', 'sticky'].includes(getComputedStyle(node).position)) { pinned = true; node.setAttribute('data-pbly-pinned', ''); }
    }
    items.push({selector: name(el), text: short, fg, pinned, need: size >= 24 || (size >= 18.66 && weight >= 700) ? 3 : 4.5,
                rects: shown.map(([left, top, w, h]) => [left + x, top + y, w, h])});
  }
  window.__pbly_text = items;
  window.__pbly_found = [];
  return clipped;
}"""

HIDE_TEXT = ("*, *::before, *::after { color: transparent !important; -webkit-text-fill-color: transparent !important;"
             " text-shadow: none !important; text-decoration-color: transparent !important; caret-color: transparent !important;"
             " transition: none !important; }")

MEASURE_SCRIPT = """async ([picture, top, last]) => {
  const image = new Image();
  image.src = picture;
  await image.decode();
  const canvas = document.createElement('canvas');
  canvas.width = image.width;
  canvas.height = image.height;
  const ctx = canvas.getContext('2d', {willReadFrequently: true});
  ctx.drawImage(image, 0, 0);
  const luminance = (c) => {
    const f = (v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
  };
  const ratio = (a, b) => {
    const [hi, lo] = [luminance(a), luminance(b)].sort((p, q) => q - p);
    return (hi + 0.05) / (lo + 0.05);
  };
  const found = window.__pbly_found;
  const height = canvas.height;
  for (const item of window.__pbly_text || []) {
    if (item.done) continue;
    // Measure each text in the first screenful that shows it whole (pinned headers only at the top of the page).
    const first = item.rects[0];
    const inside = first[1] >= top && first[1] + first[3] <= top + height;
    if (item.pinned ? top > 0 : !(inside || (last && first[1] >= top))) continue;
    item.done = true;
    const samples = [];
    for (const [x, y0, w, h] of item.rects) {
      const y = y0 - top;
      const left = Math.max(0, Math.floor(x)), top_ = Math.max(0, Math.floor(y));
      const right = Math.min(canvas.width, Math.ceil(x + w)), bottom = Math.min(height, Math.ceil(y + h));
      if (right - left < 1 || bottom - top_ < 1) continue;
      const data = ctx.getImageData(left, top_, right - left, bottom - top_).data;
      const step = Math.max(1, Math.floor(Math.sqrt((right - left) * (bottom - top_) / 300)));
      for (let j = 0; j < bottom - top_; j += step) {
        for (let i = 0; i < right - left; i += step) {
          const k = (j * (right - left) + i) * 4;
          samples.push([data[k], data[k + 1], data[k + 2]]);
        }
      }
    }
    if (!samples.length) continue;
    const a = item.fg[3];
    const measured = samples.map(bg => {
      const fg = [0, 1, 2].map(i => item.fg[i] * a + bg[i] * (1 - a));
      return {value: ratio(fg, bg), bg, fg};
    }).sort((p, q) => p.value - q.value);
    // The ratio that 90% of the background behind the text reaches: one bright pixel in a photo doesn't fail the text.
    const typical = measured[Math.floor(measured.length * 0.1)];
    if (typical.value < item.need - 0.005) {
      const spread = Math.max(...[0, 1, 2].map(i => Math.max(...samples.map(s => s[i])) - Math.min(...samples.map(s => s[i]))));
      found.push({selector: item.selector, text: item.text, fg: typical.fg, bg: typical.bg, solid: spread <= 6,
                  ratio: Math.floor(typical.value * 10) / 10, need: item.need});
    }
  }
  return found;
}"""

WAKE_SCRIPT = """async () => {
  for (const img of document.querySelectorAll('img[loading="lazy"]')) img.loading = 'eager';
  const pause = (ms) => new Promise(done => setTimeout(done, ms));
  const frame = () => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)));
  for (let y = 0; y < document.documentElement.scrollHeight; y += window.innerHeight * 0.5) {
    window.scrollTo({top: y, behavior: 'instant'});
    await frame();
    await pause(30);
  }
  window.scrollTo({top: 0, behavior: 'instant'});
  await Promise.all([...document.images].map(img => img.complete ? null :
    Promise.race([img.decode().catch(() => null), pause(3000)])));
  await pause(600);
}"""

# Where Playwright keeps Chromium on Linux, macOS and Windows.
CHROMIUM_EXECUTABLES = ("chromium-*/chrome-linux*/chrome", "chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
                        "chromium-*/chrome-mac*/*.app/Contents/MacOS/*", "chromium-*/chrome-win*/chrome.exe")


def chromium_path():
    """Prefer a Chromium that is already on the machine over asking Playwright to download one."""
    bases = [os.environ.get("PLAYWRIGHT_BROWSERS_PATH"), Path.home() / ".cache/ms-playwright",
             Path.home() / "Library/Caches/ms-playwright", os.environ.get("LOCALAPPDATA") and Path(os.environ["LOCALAPPDATA"]) / "ms-playwright"]
    for base in filter(None, bases):
        for pattern in CHROMIUM_EXECUTABLES:
            for candidate in sorted(Path(base).glob(pattern), reverse=True):
                if candidate.is_file():
                    return str(candidate)
    return None


def apply_theme(page, theme):
    page.evaluate("""([target, kind, name, value]) => {
      const el = target === 'root' ? document.documentElement : document.body;
      if (kind === 'class') el.classList.add(name); else el.setAttribute(name, value);
    }""", [theme["target"], theme["kind"], theme["name"], theme.get("value") or ""])


def browser_issues(project, widths=WIDTHS, pages=None, themes=None):
    """Return (issues, skipped notes)."""
    pages = html_pages(project) if pages is None else pages
    themes = project_themes(project) if themes is None else themes
    if not pages:
        return [], []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [Issue("browser-skipped", "", "Playwright isn't installed.")], []

    issues = []
    with sync_playwright() as pw:
        launch = {"headless": True, "args": ["--allow-file-access-from-files"]}
        try:
            browser = pw.chromium.launch(**launch)
        except Exception:
            path = chromium_path()
            try:
                if not path:
                    raise RuntimeError("no Chromium found")
                browser = pw.chromium.launch(executable_path=path, **launch)
            except Exception as exc:
                first = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
                return [Issue("browser-skipped", "", f"Chromium couldn't start: {first}")], []

        for html in pages:
            rel = html.relative_to(project).as_posix()
            for width in widths:
                for theme in [None, *themes]:
                    page = None
                    try:
                        page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=1,
                                                color_scheme="dark" if theme and theme["kind"] == "scheme" else "light")
                        found = page_issues(page, html, rel, width, theme)
                        issues += [(issue, theme and theme["label"]) for issue in found]
                    except Exception as exc:  # a page that won't load or crashes the browser shouldn't stop the report
                        first = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
                        at = f"{width}px" + (f" with {theme['label']}" if theme else "")
                        issues.append((Issue("browser-skipped", rel, f"The browser checks couldn't finish at {at}: {first}"), None))
                    finally:
                        if page is not None:
                            try:
                                page.close()
                            except Exception:
                                pass
        try:
            browser.close()
        except Exception:
            pass

    unique, seen = [], set()
    for issue, theme in issues:
        whole = issue.group in ("overflow", "cut-off")
        key = (issue.group, issue.where, theme, issue.detail if whole else issue.detail.split(" at ")[0])
        if key not in seen:
            seen.add(key)
            unique.append(issue)
    return unique, []


def page_issues(page, html, rel, width, theme=None):
    """Everything the browser can find on one page at one width; in another theme, only the colours can differ."""
    issues = []
    console_errors, page_errors = [], []
    page.on("console", lambda msg, bucket=console_errors: bucket.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc, bucket=page_errors: bucket.append(str(exc)))
    page.goto(html.as_uri(), wait_until="load")
    if theme and theme["kind"] != "scheme":
        apply_theme(page, theme)
    page.evaluate(WAKE_SCRIPT)  # scroll once so lazy images load and scroll-in animations finish
    if theme:
        return text_issues(page, rel, width, overflowing=True, theme=theme)

    scroll = page.evaluate("document.documentElement.scrollWidth")
    if scroll > width + 1:
        culprit = page.evaluate("""(width) => {
            const wide = [...document.querySelectorAll('body *')].filter(el => el.getBoundingClientRect().right > width + 1);
            const el = wide.find(el => ![...el.children].some(child => wide.includes(child))) || wide[0];
            if (!el) return '';
            return el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\\s+/).join('.') : '');
        }""", width)
        where = f" The widest element is <{culprit}>." if culprit else ""
        issues.append(Issue("overflow", rel, f"At {width}px wide the page is {scroll}px wide.{where}"))

    broken = page.locator("img").evaluate_all(
        "nodes => nodes.filter(img => img.complete && img.naturalWidth === 0).map(img => img.getAttribute('src'))")
    for src in broken:
        issues.append(Issue("image-failed", rel, f"`{src}` didn't load at {width}px."))
    for item in page_errors:
        issues.append(Issue("script-error", rel, item))
    for item in console_errors:
        if not item.startswith("Failed to load resource"):  # missing files are reported by the static check
            issues.append(Issue("console-error", rel, item))
    issues += text_issues(page, rel, width, overflowing=scroll > width + 1)
    return issues


def text_issues(page, rel, width, overflowing, theme=None):
    """Text cut off at the edge of the screen, and text that is hard to read against what is really behind it."""
    issues = []
    clipped = page.evaluate(COLLECT_SCRIPT, width)
    if not overflowing:  # a page that scrolls sideways is already reported
        for found in clipped:
            issues.append(Issue("cut-off", rel, f"<{found['selector']}> “{found['text']}” runs past the edge at {width}px."))
    # Photograph the page one screenful at a time with all text hidden (a full-page picture would stretch the
    # window and move anything sized to it), then compare each text with the pixels behind it.
    hidden = page.add_style_tag(content=HIDE_TEXT)
    pinned = None
    height = page.viewport_size["height"]
    total = page.evaluate("document.documentElement.scrollHeight")
    top, failures = 0, []
    while True:
        page.evaluate(f"window.scrollTo({{top: {top}, behavior: 'instant'}})")
        page.wait_for_timeout(60)
        actual = page.evaluate("window.scrollY")
        if actual > 0 and pinned is None:  # headers that stay on screen would cover the text under them
            pinned = page.add_style_tag(content="[data-pbly-pinned] { visibility: hidden !important; }")
        last = actual + height >= total or top + height >= total
        picture = "data:image/png;base64," + base64.b64encode(page.screenshot(animations="disabled")).decode()
        failures = page.evaluate(MEASURE_SCRIPT, [picture, actual, last])
        if last:
            break
        top += height - 100  # from where we asked, so a page that doesn't scroll still ends
    for handle in (hidden, pinned):
        if handle:
            handle.evaluate("node => node.remove()")
    page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
    for found in failures:
        kind = "large text" if found["need"] == 3 else "text"
        fg, bg = to_hex(found["fg"]), to_hex(found["bg"])
        if found["solid"]:
            shade = passing_shade(tuple(found["fg"]), tuple(found["bg"]), found["need"])
            hint = f" The closest text colour that passes: {shade}." if shade else ""
            detail = f"{fg} on {bg} is {found['ratio']:.1f}:1; {kind} needs {found['need']:g}:1.{hint}"
        else:
            detail = (f"on a photo or gradient: {fg} against {bg} behind part of it is {found['ratio']:.1f}:1; "
                      f"{kind} needs {found['need']:g}:1.")
        at = f"{width}px" + (f" with {theme['label']}" if theme else "")
        issues.append(Issue("low-contrast", rel, f"<{found['selector']}> “{found['text']}” at {at}: {detail}"))
    return issues
