# Working on this project

This is a Portably project: plain HTML, CSS and JavaScript on one design system (`tokens/tokens.json`) and the same structure as every other Portably project. There is no build step and no runtime; open `index.html` in a browser. These instructions are for AI agents and people alike.

## Read first

1. `README.md`: what the project is, its pages and known gaps.
2. `DESIGN-SYSTEM.md`: where the design came from, the assumptions and deviations, every token, and which stylesheet styles which page. Generated; don't edit it. `DESIGN-SYSTEM.html` shows the same, drawn with the tokens; open it in a browser.
3. The existing pages, `css/components/` and `js/main.js`.

Reuse what is there: the same component for the same concept, the same token for the same value, the same naming pattern for new classes. Don't redesign, simplify or "improve" the design unless asked.

## Where things go

| What | Where |
| --- | --- |
| Colours, fonts, sizes, spacing, radii, shadows, widths, the button's shape | `tokens/tokens.json` |
| Project-wide element defaults | `css/base.css` |
| Page anatomy and layouts reused across sections | `css/layout.css` |
| A recurring interface concept | `css/components/<concept>.css`, imported in `css/components.css` |
| Styles for one page | `css/pages/<page>.css`, imported in `css/pages.css` |
| Behaviour | `js/main.js`, using `data-js="…"` hooks |
| Images, icons, fonts | `assets/` |
| More pages | `pages/`, only when the design has them |

Generated, never edited by hand: `tokens/tokens.css`, `DESIGN-SYSTEM.md` and `DESIGN-SYSTEM.html` (not a page of the site; leave it out of a deploy if visitors shouldn't see it). Portably's shared CSS, never edited: `foundation/`.

## Rules

- **Every design value comes from a token.** Colours, spacing, font sizes, line heights, weights, letter spacing, radii, shadows and breakpoints are written `var(--pbly-…)`. A value close to a token is snapped to it. A deliberate one-off keeps its value with `/* exception: reason */` at the end of the line. A value needed in two or more places becomes a token with `promote`. Fluid sizes go between two tokens: `clamp(var(--pbly-font-size-2xl), 6vw, var(--pbly-font-size-5xl))`.
- **Use roles before palette colours:** `--pbly-color-text-muted` rather than the grey it points at. A see-through colour mixes a token: `color-mix(in srgb, var(--pbly-color-palette-white) 80%, transparent)`.
- **Change the system in `tokens.json`**, not in CSS custom properties, and never repeat a token's value as a fallback. Tokens you add must be used; give them a `$description` when their use needs explaining.
- **Page anatomy:** site pages are `<section class="section pricing">` > `<div class="wrapper">`, with `section-header` (`eyebrow`, `section-header__title`, `section-header__intro`) for a heading group. App screens use `app-shell` (`__sidebar`, `__topbar`, `__main`) and `panel`. Don't invent equivalents such as `container` or `section-title`.
- **Class names say what the thing is,** BEM-style: `pricing-card__price`. No utility classes (`mt-4`, `text-muted`). The only Portably classes are `pbly` on `<body>`, `pbly-btn` and `pbly-skip-link`.
- **A component is a concept that recurs** (a card, the navigation, a search form), not every wrapper that looks alike. One-page compositions stay in `css/pages/`.
- **Semantic, accessible HTML:** real buttons and links, labelled fields, alt text, a sensible heading order, visible focus, readable contrast (4.5:1, or 3:1 for large text). No ARIA where native HTML already says it.
- **JavaScript is behaviour only:** it targets `data-js` hooks, not styling classes, and keeps `aria-expanded` and similar state in step with what happens.
- **Build only what the design or the request contains.** No pages or states added to demonstrate reuse.
- **Shared parts are repeated, not generated.** There is no build step, so the header, navigation and footer are copied into every page. Keep the copies identical: change one, change them all.
- **Layouts follow the content** (Grid, Flexbox, `minmax()`, `clamp()`) before breakpoints; nothing scrolls sideways on a phone.
- **A page that is neither stacked sections nor an app screen** (documentation with a sidebar, for example) keeps `wrapper` for its width and defines its layout in `css/layout.css` under a project name, such as `docs-layout`. Record it under "This project's conventions".
- **Keep it self-contained:** local assets in `assets/`. Links to other websites stay as they are; a link to a page of this site that isn't built yet points at the closest section, not `#`, and is listed in the README.
- HTML comments are short section labels. Explanations go in the README or `portably.config.json`.

## Record decisions

What the next person needs to know goes into `portably.config.json` as plain sentences; `check` lists it in `DESIGN-SYSTEM.md`:

- `"source"`: where the design came from (a Figma file and its frames, screenshots, a website, a brief) and when.
- `"assumptions"`: decisions made where the source was silent or unclear, such as a hover colour or a mobile layout nobody designed.
- `"deviations"`: deliberate differences from the source, such as a substituted font, a missing image or a change that was asked for.
- `"normalizations"`: values snapped to a token, for example "14px and 15px captions → `font.size.sm`". `fix` records its own.
- `"readability"`: design colours changed to pass contrast, for example "color.palette.green #00915E → #008855: white button text needs 4.5:1".

## This project's conventions

Conventions this project settles on that the rules above don't cover (a shared grid class, how dialogs open, an icon approach), so the next person reuses them:

- `index.html` is the introduction; every other page lives in `pages/`.
- Every page repeats the same header, sidebar (`docs-nav`) and footer. When you add, rename or reorder a page, update the sidebar on every page and the previous and next links around it. A test checks that the sidebars match.
- A page is `wrapper docs-layout` holding `docs-nav`, `main.docs-layout__main` with `article.prose`, and `docs-toc`. Each part of the article is a `<section id="…">` with an `<h2>`, and "On this page" links to every section id.
- Code samples are `<div class="code-block" data-js="code-block"><pre class="code-block__pre"><code>`, with `<` and `>` escaped; `js/main.js` adds the copy button.
- The theme is dark by default. The light theme points the colour roles at the light palette in `css/base.css`, under `:root[data-theme="light"]`. The choice is stored as `portably-theme` in the browser, and one line in each page's `<head>` applies it before the page draws.
- `color.brand.*` (the logo's magenta and blue) is decoration only, never text.
- `pages/findings.html` lists every finding kind in `tools/report.py`; a test checks that none is missing.

## Check your work

Portably is a separate download, not part of this project: `git clone https://github.com/devygits/portably` next to this folder. `"portably"` in `portably.config.json` says which version the project follows.

```bash
python ../portably/portably.py check .            # every finding, explained
python ../portably/portably.py check . --json     # the same findings as data
python ../portably/portably.py fix .              # the safe fixes, then check again
python ../portably/portably.py promote . spacing 80px
```

- **Problems:** fix them; `fix` handles the mechanical ones.
- **Decisions:** snap to a token, mark a deliberate one-off `/* exception: reason */`, or run the `promote` command shown.
- **Notes:** resolve them, or say in the README why they stay.

Finish with `check . --strict`. The browser checks (text contrast, sideways scrolling, text cut off, broken images and script errors at 390px and 1440px) need Playwright: `pip install playwright`, then `playwright install chromium`. They render every theme the CSS defines, too: a dark mode, a theme toggle. `--no-browser` records a note and therefore does not pass a strict handoff. **Do not substitute your own validation for the final Portably check.** If the real strict check cannot run, report that blocker instead of claiming the project is complete.

A finished handoff contains the generated `tokens/tokens.css`, `DESIGN-SYSTEM.md` and `DESIGN-SYSTEM.html` from that final check.

## Moving to another stack

`tokens/tokens.json` uses the design-tokens (DTCG) format, and `tokens/tokens.css` is plain CSS custom properties, so the system moves as it is. Each file in `css/components/` is one component; `DESIGN-SYSTEM.md` lists the classes it styles and the pages that use it. Keep the class names and tokens when porting to React, Vue, Astro or a WordPress theme, and the design moves with them.
