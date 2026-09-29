# Design-system contract

Every Portably project implements its interface through one complete design system recorded in `tokens/tokens.json`. The source design supplies the values; Portably supplies the shape of the system, the defaults for anything the source leaves undefined, and the check that the implementation follows it.

This applies whatever the source is: a precise Figma file, an inconsistent design, a screenshot, an existing application being standardised, or no design at all.

## 1. The system is always complete

`tokens.json` must contain every token listed in `standard/system-policy.json` under `requiredTokens`:

- **colour roles**, including the action hover state;
- **type scale**: body font, the `font.size` scale, the four weights and the five typography roles;
- **spacing scale**: every baseline step in `standard/spacing-scale.json`, with its baseline value;
- **radius** and **shadow** scales;
- the **button** shape: `button.radius`, `button.padding-block`, `button.padding-inline`, `button.min-height`, `button.font-weight`;
- **layout** widths, gutter and measures.

When the source does not define one of these, keep the starter's default. A project may change values (brand colours, font sizes, radii, shadows) and may add tokens. Baseline spacing steps keep their values because their names encode them.

## 2. Every design value comes from a token

In project CSS (`css/**/*.css`) and in inline HTML styles, these values must be written with `var(--pbly-…)`:

| What | Properties | Compared against |
| --- | --- | --- |
| Colours | any property | colour tokens |
| Spacing | `margin*`, `padding*`, `gap`, `row-gap`, `column-gap` | `space.*` |
| Font size | `font-size` | `font.size.*` |
| Line height | `line-height` | `font.line-height.*` |
| Letter spacing | `letter-spacing` (`px`, `rem` or `em`) | `font.tracking.*`, in the same kind of unit |
| Font weight | numeric `font-weight` | `font.weight.*` |
| Radius | `border-radius` and its longhands | `radius.*` |
| Shadows | `box-shadow`, `text-shadow` | `shadow.*` |
| Breakpoints | lengths in `@media` conditions | `standard/breakpoints.json` + project config |

Not checked: border widths, element widths/heights, positions, transforms, transitions, the `font` shorthand, `@font-face` descriptors, and SVG attributes. Neutral values are always allowed: `0`, `auto`, percentages, viewport units, `fr`, `line-height: 1`, `font-size: 1em`, keywords such as `inherit`, `transparent` and `currentColor`.

A semi-transparent colour follows the system when its base colour is a token:

```css
background: color-mix(in srgb, var(--pbly-color-palette-white) 80%, transparent);
```

## 3. Small inconsistencies snap

A hand-written value close to a token is treated as an accident and replaced by that token. `portably.py fix` makes the replacement and records it. "Close" is defined in `standard/system-policy.json`:

| Value | Snaps when within |
| --- | --- |
| spacing | 2px of a step |
| radius | 2px of a step |
| font size | 1px of a size |
| line height | 0.05 of a step (1.3 → 1.25) |
| colour | ΔE 2.3 (a difference most people cannot see) |
| shadow | 1px in each offset/blur, and a matching colour |

A value exactly halfway between two steps rounds up. Values smaller than the smallest step are never snapped; hairline adjustments are treated as deliberate.

Every snap is recorded in `"normalizations"` in `portably.config.json` and listed in `DESIGN-SYSTEM.md` (section 6). `fix` records its own snaps; a snap made while writing the CSS is added to that list by hand.

A size that scales with the screen goes between two tokens and needs no exception:

```css
.hero__title { font-size: clamp(var(--pbly-font-size-2xl), 6vw, var(--pbly-font-size-5xl)); }
```

When a value matches more than one colour role (white is both `color.surface.raised` and `color.action.on-primary`), `fix` chooses by property (`color` → text roles, `background` → background and surface roles, `border`/`outline` → border roles; action colours fit all three) and never crosses kinds: when the only match is another kind of role, it uses the palette colour. It leaves the value for a person when the choice is still ambiguous.

## 4. Deliberate one-offs are logged exceptions

A value further from the system than the snap distance is deliberate. When it is used **once**, it stays in the CSS with an exception comment at the end of its line. The comment excuses the value on that line that needs it:

```css
.hero { padding-block: 5rem; /* exception: hero spacing from the design */ }
```

For a breakpoint, put the comment on the `@media` line. The reason must say why the value exists.

## 5. Repeated values become part of the system

When the same deliberate value is needed in **two or more places** (with or without exception comments), it is a missing token, not an exception. The check reports it once, with the command that adds it:

```bash
python portably.py promote <project> spacing 80px
python portably.py promote <project> radius 20px --as radius.xl
python portably.py promote <project> font-size 22px --as font.size.lead
python portably.py promote <project> line-height 1.4 --as font.line-height.comfortable
python portably.py promote <project> shadow "0 2px 6px rgba(0, 0, 0, 0.3)" --as shadow.card
python portably.py promote <project> colour "#E11D48" --as color.palette.rose
python portably.py promote <project> breakpoint 1200px --as wide
```

`promote` adds the token (or breakpoint), uses it wherever the value appears, and removes exception comments that are no longer needed. It is the only way Portably changes the design system, and it runs only when asked.

- **Spacing** gets a new step. Step names follow the baseline rule, key = px ÷ 4 with `-5` for a half step: 80px → `space.20`, 90px → `space.22-5`. Values that are not a whole or half step of 4px should be rounded to the nearest 2px.
- **Colours, sizes, radii, shadows** get a new token in the matching group.
- **Breakpoints** are added to the project's `portably.config.json`:

```json
{
  "namespace": "pbly",
  "breakpoints": { "wideMaxPx": 1200 }
}
```

## 6. DESIGN-SYSTEM.md documents the system

`portably.py check` writes `DESIGN-SYSTEM.md` in the project root. It contains:

- **where the design came from**: the `"source"`, `"assumptions"` and `"deviations"` recorded in `portably.config.json`;
- what the project **changed** from the Portably defaults and what it **added**, with each token's `$description`;
- the **pages and components**: each stylesheet in `css/components/` and `css/pages/`, the classes it styles and the pages that use them;
- the colour roles and palette, type scale, weights, line heights, text styles, spacing, radii, shadows, layout widths and breakpoints;
- **normalizations**: what was snapped (for example "14px and 15px captions → `font.size.sm`");
- **changed for readability**: design colours adjusted to meet the contrast minimums, from `"readability"` in `portably.config.json`;
- **exceptions**: every `/* exception: reason */` in the CSS, with its location.

The file is generated; it is never edited by hand. It is the page a developer reads before extending the project.

`check` also writes `DESIGN-SYSTEM.html` from the same data: every colour, text style, size, spacing step, radius, shadow and the button drawn with the project's own `foundation/` and `tokens.css`, the contrast of each colour pair, and links to the pages. The project's own fonts and themes come with it: the page opens in the theme named in its address (`DESIGN-SYSTEM.html?theme=light`), and has one button to switch to the project's light or dark theme. Shown inside another page (`DESIGN-SYSTEM.html?embed`), it leaves the theme button to that page. A sidebar lists its sections; on a phone it opens from a menu button. It isn't one of the project's pages: the page checks and the unused-token check skip it.

## 7. The token file format

`tokens.json` uses a documented subset of the Design Tokens Community Group (DTCG) format, so design tools and other stacks can read it. Portably doesn't claim full DTCG conformance; this section and the exporter tests define what is supported.

- Nested groups and tokens, named with letters, numbers, `_` and `-`. `$description` and other `$` metadata are kept for people and ignored by the exporter.
- Types: `color`, `dimension`, `fontFamily`, `fontWeight`, `number`, `shadow`, `typography`.
- Colours are written the way designers copy them: `#2F6B4F`, `rgb(47 107 79)`, `hsl(152 39% 30%)`, `oklch(0.48 0.08 161)` or `oklab()`, with an optional `/ alpha`. The token CSS keeps the value as written; the check compares every colour in sRGB. The DTCG object form (`{"colorSpace": "srgb", "components": […], "hex": "…"}`) also works.
- Dimensions in `px` and `rem`, plus `em` for letter spacing (`font.tracking.*`, a Portably addition).
- Font families as a string or a list of strings; numeric weights and numbers.
- One shadow object with offsets, blur, spread, colour and optional `inset`.
- Typography composites with exactly `fontFamily`, `fontSize`, `fontWeight`, `letterSpacing` and `lineHeight`.
- Whole-token aliases such as `{color.palette.accent}`, including inside typography composites. Missing, circular and mismatched aliases and colliding CSS names are errors.

Not supported: other structured colour spaces, gradients, border or transition composites, several shadows in one token, group inheritance, and modes inside the token file (modes are CSS overrides; see `THEMING.md`).

## 8. Text must be readable

The check applies the WCAG AA contrast minimums: 4.5:1 for normal text, 3:1 for large text (24px, or 18.66px bold) and for form-field borders and buttons against the page.

- **Always**, from tokens alone: every text role (`text.primary`, `text.muted`, `text.soft`) on `background` and `surface.raised`; `action.on-primary` on `action.primary` and `action.hover`; `action.primary` and `border.strong` against the page.
- **In the browser**, on every page at 390px and 1440px: each piece of visible text against what is actually behind it on screen. Portably photographs the page with the text hidden and compares the text colour with those pixels, so photos, gradients and overlays count like solid colours. On a photo the text must reach the ratio against 90% of the pixels behind it. Disabled controls are exempt.

When a colour pair fails, the report gives the closest shade that passes (same hue, lighter or darker). If that changes a colour from the design, record it in `portably.config.json`:

```json
"readability": ["color.palette.green #00915E → #008855: white button text needs 4.5:1"]
```

The browser check also renders every theme the project's CSS defines: a rule that points the colour roles elsewhere under an attribute or class on `:root`, `html`, `<body>` or the namespace class (`.pbly[data-theme="dark"]`, `html.dark .pbly`), or inside `@media (prefers-color-scheme: …)`. A finding in a theme says which one (`with data-theme="dark"`). Hover and focus states are not rendered; check them by hand.

The browser checks need Playwright. When they couldn't run, `check` says so as a Safety note, so `--strict` fails; `--no-browser` turns them off on purpose.

## 9. Other rules the checker enforces

- **No changed base size.** Every `rem` token assumes the browser's 16px root. `html { font-size: 106.25% }` rescales the whole system, so the check reports it; put the design's real sizes in `tokens.json` instead.
- **No token fallbacks.** `var(--pbly-radius-md, 8px)` copies the token's value and goes stale when the token changes. Write `var(--pbly-radius-md)`.
- **No hidden token systems.** A custom property defined in project CSS may point at tokens (`--card-bg: var(--pbly-color-surface-raised)`), but it may not hold a raw design value. Raw values belong in `tokens.json`. Theme overrides of `--pbly-*` roles point at palette tokens rather than raw colours.

## Running the check

```bash
python portably.py check <project>
python portably.py fix <project>
```

The check lists every finding in one run. Values that match or nearly match a token are **problems** that `fix` resolves; values outside the system are **decisions** (snap, exception or promote); an exception comment on a value that now follows the system is a **note** that `fix` removes.
