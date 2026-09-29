# Themes and modes

Portably treats **semantic tokens as the theming API**. It does not prescribe a brand palette or require a theme runtime. Examples use the default `pbly` namespace; a generated project namespace changes the CSS prefix/scope but not the token paths or theming model.

## Project themes

A project changes the values behind semantic roles; it does not rename public classes or edit foundation stylesheets. The normal way is to edit the role or palette values in `tokens.json` and regenerate `tokens.css`.

## Modes

Add the mode's colours to the palette in `tokens.json` (for example `color.palette.night`, `color.palette.snow`), then use a stable attribute or host condition to point the **semantic** roles at them. Do not duplicate component CSS for a dark mode or brand variation, and do not put raw colours in the override; the design-system check flags them.

```css
.pbly[data-theme="dark"] {
  --pbly-color-background: var(--pbly-color-palette-night);
  --pbly-color-text-primary: var(--pbly-color-palette-snow);
  --pbly-color-text-muted: var(--pbly-color-palette-mist);
  --pbly-color-surface-raised: var(--pbly-color-palette-night-raised);
  --pbly-color-border-default: var(--pbly-color-palette-slate);
}
```

For an automatic system preference, a project may place the same semantic overrides inside `@media (prefers-color-scheme: dark)`.

`check` finds both kinds of theme in the project's CSS and measures the text of every page in each one, as well as in the default (`SYSTEM.md`, section 8).

## Sections with their own colours

The same pattern works for any number of contexts, for example a page that alternates dark, light and paper-coloured sections. Give each a class on the section and point the roles at palette tokens:

```css
.pbly .ground-dark {
  --pbly-color-background: var(--pbly-color-palette-pine);
  --pbly-color-text-primary: var(--pbly-color-palette-snow);
  --pbly-color-text-muted: var(--pbly-color-palette-sage);
  --pbly-color-border-strong: var(--pbly-color-palette-pine-line);
  background: var(--pbly-color-background);
  color: var(--pbly-color-text-primary);
}
.pbly .ground-paper { --pbly-color-background: var(--pbly-color-palette-paper); /* … */ }
```

When a context needs a role Portably doesn't have (a chip background, a third text tier), add it to `tokens.json` under `color.*` like any other token and override it the same way. The browser check measures the text in every context, so each one must be readable on its own.

## Why modes remain project-owned

The portable core defines *how* themes override roles, not which themes a product must have. A marketing site, dashboard and embedded widget can therefore use the same system without inheriting irrelevant theme names or palettes.

The cascade (which rules win against layered tokens and host CSS) is described in `FOUNDATION.md`.
