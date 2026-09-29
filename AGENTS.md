# AGENTS.md

Portably is how an AI agent turns a design into a structured, documented frontend project: plain HTML, CSS and JavaScript on one complete design system, in a structure every Portably project shares, verified by one command (`python portably.py check`).

The design source decides **what** is built: how it looks, what it contains, how it behaves. Portably decides **how** it is organized and which design system every value comes from. The finished project must be easy to continue for you, another agent or a developer, and easy to move into another stack later.

Portably is not a visual style, a component library or an application framework. Two designs built with Portably should look nothing alike and feel equally familiar in source.

If you are changing Portably itself rather than building a project with it, read `DEVELOPMENT.md` instead.

## The workflow

1. **Inspect** the source and anything already built (below).
2. **Create or open the project.** New: `python path/to/portably/portably.py init site` in the workspace, never inside the Portably folder. Existing: read its `AGENTS.md`, `README.md` and `DESIGN-SYSTEM.md` first.
3. **Read the project's `AGENTS.md`.** It holds the working rules: where things go, the value rules, the page anatomy and naming. They are the same in every project, and they are what the next agent will follow.
4. **Record the source** in `portably.config.json`: `"source"` says where the design came from and when.
5. **Tokens first:** put the design's decisions into `tokens/tokens.json` before writing page CSS.
6. **Build the pages** on the page anatomy, reusing the project's existing components and conventions.
7. **Check as you go:** `python portably.py check site --json`. Run `fix` for the safe changes, then resolve every decision explicitly.
8. **Record the decisions** that aren't visible in the code, and finish with `python portably.py check site --strict`.

## 1. Inspect before coding

The source may be a Figma file, screenshots, an existing website or HTML/CSS, wireframes or a written brief. Identify the requested pages and states, shared visual values, recurring interface concepts, page-specific compositions, responsive behaviour, interactions, assets and content.

- **Build only what the source contains or the user asks for.** Never create extra pages or states to demonstrate Portably, component reuse, routing or the project structure.
- **Don't redesign.** Don't simplify or "improve" the design unless asked.
- **Do normalize small inconsistencies** into the system: a 15px gap among 16px gaps, 14px and 15px captions for the same kind of text, a colour one shade off a brand colour. The source may be inconsistent; the implementation may not.
- **Where the source is silent or ambiguous**, make the smallest reasonable decision and record it in `"assumptions"`.
- **Where an asset is unavailable** (an image, font or icon), use the closest reasonable substitute and record it in `"deviations"`.
- Don't invent a component system from isolated screenshots.

## 2. The project boundary

The project lives in its own folder, created with `init`. If Portably isn't on the machine yet, download it into a folder of its own (a temporary folder, or `portably/` next to the project), not into the project. Don't copy Portably's `tests/`, `docs/`, `standard/` or `tools/` into the deliverable.

Replace the starter's placeholder content with the supplied design. Don't keep starter sections or components just because they exist.

## 3. Record the design system in tokens

Before page CSS, record the source's decisions in `tokens/tokens.json`:

- brand colours in `color.palette.*`, pointed at by the roles (`color.text.*`, `color.action.primary` and `.hover`, `color.surface.raised`, `color.border.*`);
- fonts, sizes, weights, line heights and letter spacing (`font.tracking.*`, in `px`, `rem` or `em`), and the text styles (`text.*`);
- the spacing rhythm, radii and shadows;
- content widths: `layout.wrapper.max` is the content width without the side margins; `layout.section.padding` is the space above and below each section, so sections 72px apart use 36px;
- the button's shape (`button.*`). Never edit `foundation/`; restyle the button through its tokens.

Write colours the way the source gives them: `#2F6B4F`, `rgb()`, `hsl()` or `oklch()`. Where the source is silent (a screenshot, a wireframe, no design), keep the starter's defaults; the system must stay complete (`standard/SYSTEM.md` lists what it contains). Edit `tokens.json` only; `check` regenerates `tokens.css`.

If a design colour is too faint to read, `check` reports it with the closest shade that passes. Use that shade and add a line to `"readability"`, for example "color.palette.green #00915E → #008855: white button text needs 4.5:1".

Then every design value in project CSS and inline styles comes from a token:

1. **Exists in the system → use the token.**
2. **Close to a token → snap to it.** Within 2px for spacing and radius, 1px for font size, 0.05 for line height, or a colour difference most people can't see. `fix` snaps hand-written values and records them; when you snap while writing, add a line to `"normalizations"`.
3. **Deliberate and used once → a logged exception** at the end of its line: `padding-block: 5rem; /* exception: hero spacing from the design */`.
4. **Deliberate and used in two or more places → a new token.** Run the `promote` command `check` prints (`python portably.py promote site spacing 80px`); it adds the token and uses it everywhere. A new spacing step is named px ÷ 4 (80px → `space.20`).

A size that scales with the screen goes between two tokens and needs no exception: `font-size: clamp(var(--pbly-font-size-2xl), 6vw, var(--pbly-font-size-5xl))`. A static desktop size on a big headline usually runs off the edge of a phone.

## 4. Converting existing code

When the source is existing HTML/CSS, port what it looks like and does, not its implementation:

- Utility classes (`u-h1`, `mt-5`, `text-muted`, Tailwind) become a name for what each element is, with the values in that rule. A class naming a layout relationship reused across sections (`split`, `card-grid`) belongs in `css/layout.css`; a class naming a value belongs nowhere.
- The source's CSS variables become tokens in `tokens.json`, not project custom properties.
- Its framework, build step and dependencies stay behind unless the user asks to keep them.

## 5. Check, fix, decide

From the Portably folder, point the command at the project:

```bash
python portably.py check site --json     # findings as data; drop --json for the explained report
python portably.py fix site              # safe fixes only, then checks again
python portably.py check site --strict   # before handoff: notes count too
```

`check` regenerates `tokens.css`, `DESIGN-SYSTEM.md` and `DESIGN-SYSTEM.html`, then reports Safety, Design system, Structure and Handoff findings. It also opens every page in a browser at 390px and 1440px (text contrast against what's really behind it, text cut off at the edge, sideways scrolling, broken images, script errors). That needs Playwright: `pip install playwright`, then `playwright install chromium`. If the machine really can't run it, `--no-browser` records a Safety note, so `--strict` still fails; say so in the README and in your summary. **Do not substitute your own validation for the final Portably check.** If the real `check --strict` cannot run to completion, the project is not complete: report the blocker instead of recreating the check or claiming handoff readiness.

Each JSON finding has a `kind`, `area`, `level`, `file`, `line`, `detail`, whether it is `fixable`, whether it is a `decision`, and the `command` that resolves it when there is one.

- **Problems** must be fixed. `fix` handles the mechanical ones.
- **Decisions** need a judgement: snap the value to a token, mark a deliberate one-off with `/* exception: reason */`, or run the `promote` command shown.
- **Notes** are resolved where practical; otherwise the README says why the project keeps them.

Fix what `check` reports; never hide text or code from it, and never edit Portably's `tools/` to silence a finding. Don't claim completion while a requested width scrolls sideways by accident.

## 6. Record what the code can't show

`portably.config.json` keeps the decisions, and `check` lists them in `DESIGN-SYSTEM.md`. Write each as one plain sentence:

| Key | What |
| --- | --- |
| `"source"` | where the design came from (a Figma file and its frames, screenshots, a URL, a brief) and when |
| `"assumptions"` | decisions made where the source was silent or unclear, including values you inferred |
| `"deviations"` | deliberate differences from the source: substitutions, simplifications, changes that were asked for |
| `"normalizations"` | values snapped to a token (`fix` records its own) |
| `"readability"` | design colours changed to pass contrast |

The README lists the pages and states, remote dependencies and known gaps. A convention the project settles on (a shared grid class, how dialogs open) goes under "This project's conventions" in the project's `AGENTS.md`, so the next agent reuses it. HTML comments stay short section labels; they ship to every visitor.

## 7. Keep it small

Unless the user asks, don't add React/Vue/Svelte, Tailwind/Bootstrap, a build step, package dependencies, a component library, CSS-in-JS, a new Portably class or namespace, or abstraction layers around ordinary HTML/CSS. If native HTML/CSS/JS implements the design cleanly, use it. Prefer local assets under `assets/`; a remote font, script or image is a dependency to list in the README.

Don't change Portably to make one design fit. Use project CSS for project needs, and record genuine friction in the method separately:

```text
What I tried:
What was unclear or difficult:
What I expected:
What I did instead:
Classification: universal / recurring / project-specific
```

## Done means

- semantic HTML for every requested page and state, on the page anatomy;
- CSS in the right files, every design value from a token or a logged exception;
- `tokens.json`, and `tokens.css` generated from it;
- JavaScript for the interactions the source shows, on `data-js` hooks;
- local assets with understandable names;
- `portably.config.json` with the source and every assumption, deviation, normalization and readability change;
- a README with the pages, remote dependencies and known gaps;
- the real `check --strict` command passing, run last so `tokens/tokens.css`, `DESIGN-SYSTEM.md` and `DESIGN-SYSTEM.html` are current and present in the handoff.

The project must be understandable without access to the conversation that produced it.