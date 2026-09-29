# Changelog

From 1.0 the contract in `standard/` is stable. A change that would break an existing project is marked **Breaking** and waits for the next major version. Additions are not breaking.

## 1.0

The first public release. Portably gives an AI agent a predictable system to build a design into, and leaves behind a repository that anyone can continue.

- **One command:** `python portably.py` with `init`, `check`, `fix` and `promote`. `check --json` prints the same findings as data for agents.
- **One design system:** every project records its colours, type, spacing, radii, shadows, widths and button shape in `tokens/tokens.json` (design-tokens format). Every design value in the project's CSS must come from it; small differences snap to a token, deliberate one-offs are logged, repeated values are promoted.
- **One structure:** the same files, the same page anatomy (`section` and `wrapper` for sites, `app-shell` and `panel` for applications) and readable project class names.
- **A check that looks at the result:** design system, structure and handoff, plus a rendered check at 390px and 1440px for text contrast (in every theme the project defines), sideways scrolling, text cut off, broken images and script errors.
- **A project that explains itself:** `AGENTS.md`, `portably.config.json` (design source, assumptions, deviations) and the generated `DESIGN-SYSTEM.md` and `DESIGN-SYSTEM.html`.
- **Documentation:** a documentation site, itself built with Portably, with a dark and a light theme.

## Development history

Versions before 1.0 are the milestones the project passed through. They were numbered afterwards and were never public releases.

### 0.10

The workflow is organised around an AI agent building from a design. Every project carries its own `AGENTS.md` and records the design's source, assumptions and deviations in `portably.config.json`. `check` writes `DESIGN-SYSTEM.md` and `DESIGN-SYSTEM.html`, `--json` reports findings as data, projects record the Portably version they follow, and a strict check fails when the browser checks did not run.

### 0.9

One command replaces the separate scripts: `init`, `check`, `fix` and `promote`. The button takes its shape from `button.*` tokens, colours can be written as hex, `rgb()`, `hsl()` or `oklch()`, letter spacing is part of the system, and the check measures contrast against what is really on screen. The rendered check names the element that makes a page too wide.

### 0.8

A fixed page anatomy for every project: `section`, `wrapper` and `section-header` for sites, `app-shell` and `panel` for applications. The foundation shrinks to the scoped reset, the button and the skip link.

### 0.7

Design-system enforcement. Every design value in project CSS and inline styles must come from a token. Small inconsistencies snap to the nearest token, one-off values carry a logged exception, and every project keeps a complete system with a hover state, a type scale, spacing, radii, shadows and layout widths.

### 0.6

The starter becomes a self-contained project scaffold, and the checks learn to work on the project they are pointed at. CSS scales through `css/components/` and `css/pages/`. Handoff checks catch broken links, missing files, remote dependencies and sideways scrolling. Three projects built by AI agents from a screenshot, a Figma file and an existing page shaped these changes.

### 0.5

Human-readable markup. The starter uses semantic HTML and descriptive project classes on top of the shared tokens and button.

### 0.4

The name Portably and a configurable namespace (`pbly` by default), so Portably's classes and custom properties never collide with the site or application a project ends up inside.

### 0.3

An accessibility contract, an enforced policy for unused tokens, and a regression test that injects generic host CSS to confirm the namespaced button still wins.

### 0.2

Cascade layers for the reset and the generated tokens, project themes and modes through semantic roles, and token usage analysis.

### 0.1

The foundation: design tokens in the design-tokens format exported to CSS, a scoped reset, a button, a starter project and a documentation site.
