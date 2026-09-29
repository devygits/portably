# Foundation contract

## Scope and principle

The foundation is the small set of CSS every Portably project shares: a scoped reset with focus and reduced-motion handling, the button, and the skip link. It defines **no brand and no layout**; layout is the page anatomy in the project's `css/layout.css` (`STRUCTURE.md`). Projects never edit `foundation/`; `check` reports changes and `fix` restores the originals.

## Namespace

Portably's public names share one prefix, the **namespace**: `pbly` by default. It keeps Portably's names from colliding with the site or application a project ends up inside (a WordPress theme, a Bootstrap page, a React app). It controls four identifiers together:

| Identifier | Default | With `--namespace acme` |
| --- | --- | --- |
| opt-in scope | `.pbly` | `.acme` |
| class prefix | `pbly-btn` | `acme-btn` |
| custom-property prefix | `--pbly-color-action-primary` | `--acme-color-action-primary` |
| low-precedence layers | `pbly-reset`, `pbly-tokens` | `acme-reset`, `acme-tokens` |

```bash
python portably.py init ../acme-site --namespace acme
```

Rules:

1. A namespace starts with a lowercase letter and contains only lowercase letters, numbers and single hyphens. It can't be empty: the prefix is part of the collision strategy.
2. Choose it when the project starts; it is recorded in `portably.config.json`. Changing it later changes classes, custom properties and layer names across the project.
3. Token paths don't change with the namespace: `color.action.primary` is `--pbly-color-action-primary` or `--acme-color-action-primary`.
4. Project classes never use the namespace (`property-card`, not `acme-property-card`).

Portably's own source uses `pbly`; `init` writes the chosen namespace into every generated file.

## Cascade and host integration

Cascade layers are limited to low-precedence infrastructure:

```css
@layer pbly-reset, pbly-tokens;
```

The reset and the generated token declarations are layered, so host and project CSS override them. **The button and skip-link rules are unlayered**: their `.pbly .pbly-*` specificity competes normally with unlayered host CSS instead of automatically losing to it. Project CSS is also unlayered and loads after the foundation and tokens.

Generic selectors target descendants of the scope (`.pbly a`, never a global `a`), so a project can live in part of an existing page. This is collision **mitigation**, not isolation: a later host rule with equal or higher specificity, or a host `!important`, still wins. Resolve real collisions with ordinary integration CSS; use an iframe or Shadow DOM when hard isolation is a requirement. `tests/browser_check.py` injects generic unlayered host `button` rules after the foundation and checks that the namespaced button still wins.

## Design tokens

- `tokens.json` is the source of truth, in the DTCG-compatible subset described in `SYSTEM.md`; `tokens.css` is generated from it and never edited.
- Palette values → semantic roles → optional component tokens (such as `button.*`). Shared CSS uses semantic roles, not palette values.
- The typography roles `text.heading.lg`, `text.heading.md`, `text.body.md`, `text.body.lg` and `text.label.sm` hold family, size, weight, letter spacing and a unitless line height. The reset uses `text.body.md` for body text.
- No fixed pixel root font size: `rem` spacing and type follow the reader's font-size preference.
- Spacing steps are nominal pixels at a 16px root: each whole step is 4px and `space.5 = 1.25rem = 20px` (`standard/spacing-scale.json`).
- Baseline tokens a design doesn't need may stay unused (`standard/token-policy.json` lists them); tokens a project adds must be used.

## Layout

The foundation contains no layout classes and no breakpoints. The default breakpoints are in `standard/breakpoints.json` (max 980px and max 640px), extendable per project in `portably.config.json`.

## HTML and behaviour

- Use `<header>`, `<main>`, `<footer>` and a sensible heading order; `<button type="button">` for actions and `<a href>` for links.
- Keep lists and links recognizable by default; layouts opt into list resets when they need them.
- Keep keyboard focus visible and respect reduced motion (`ACCESSIBILITY.md`).
- Behaviour and business logic belong to the project.
- Comments explain unobvious intent; no ornamental banners.

## The button

The button is the only styled shared component. `.pbly .pbly-btn` provides the structure; `pbly-btn--primary` and `pbly-btn--secondary` the role-based appearance. Its shape comes from the `button.*` tokens (radius, padding, minimum height, font weight) and its colours from the `color.action.*` roles, so a project matches its design in `tokens.json`. A change the tokens can't express (a gradient, an icon-only variant) goes in project CSS on the project's own class or a modifier.

## Limits

The checks don't certify WCAG, complete CSS validity, hard isolation or full DTCG conformance.
