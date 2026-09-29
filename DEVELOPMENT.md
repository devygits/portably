# Developing Portably

This file is for maintainers of Portably itself. A client project does not need most of these files.

## Normal source checks

Requires Python 3.9 or newer.

```bash
python portably.py check starter --framework --strict
python -m unittest discover -s tests -p "test_*.py" -v
```

`--framework` adds the maintainer checks: the canonical foundation's contract, starter/foundation synchronization, generated starter files and the docs page. `check` rewrites `starter/tokens/tokens.css`, `starter/DESIGN-SYSTEM.md` and `starter/DESIGN-SYSTEM.html`; commit them when they change (CI fails if they are stale). Run `python portably.py check docs --strict` too: the documentation site is itself a Portably project.

GitHub Actions runs both commands on every pull request, with `--no-browser`.

## How the command is built

`portably.py` is a thin command line over the modules in `tools/`:

| Module | Job |
| --- | --- |
| `check.py` | runs every check and returns issues; regenerates `tokens.css`, `DESIGN-SYSTEM.md` and `DESIGN-SYSTEM.html` |
| `check_system.py` | judges every design value in project CSS and inline styles against the tokens |
| `check_handoff.py` | links, files, images, alt text, anatomy, README, remote dependencies |
| `check_browser.py` | rendered checks (overflow, images, script errors) when Playwright is installed |
| `themes.py` | finds the themes a project's CSS defines, for the rendered checks and `DESIGN-SYSTEM.html` |
| `report.py` | the plain-language catalogue (title, why, what to do), the grouped report and the `--json` data |
| `fix.py` | `fix` (safe rewrites) and `promote` (adds tokens, rewrites uses) |
| `design_doc.py` | gathers the design system once and writes `DESIGN-SYSTEM.md`, including the design context and the stylesheet-to-page map |
| `design_page.py` | renders the same gathered data as `DESIGN-SYSTEM.html`, drawn with the project's tokens |
| `project.py` | `init`, and the README/AGENTS templates `fix` restores |
| `framework.py` | maintainer checks for Portably's own source |
| `build_tokens.py`, `analyze_tokens.py`, `naming.py` | token export, unused tokens, namespaces |

Every finding kind has an entry in `report.GROUPS` with a title, why it matters and what to do; a test fails if one is missing. When you add a check, write those three sentences for a designer reading them for the first time. The text report and `--json` are two renderings of the same `Issue` list; never add a check to only one of them. Finding kinds and JSON keys are read by agents and tools: rename one only as a breaking change, and bump `JSON_FORMAT` in `report.py` when the shape of the data changes.

Thresholds and required tokens live in `standard/system-policy.json`; the contract is `standard/SYSTEM.md`.

## Browser checks

`check` runs the rendered checks when the Playwright Python package is installed (`pip install playwright`, then `playwright install chromium`). If Playwright can't find its own Chromium, it tries one under `PLAYWRIGHT_BROWSERS_PATH`. `tests/browser_check.py` is a separate smoke test for Portably's own starter and docs pages.

## Client starter boundary

`starter/` is what `init` copies. It contains a synchronized copy of the canonical foundation so the starter itself renders and passes the check.

The starter intentionally contains only one HTML page. It must not imply that projects should invent extra pages to demonstrate reuse.

## Versions

The Portably version lives in the root `portably.config.json` (`"version"`). `init` writes it into each project as `"portably"`, and `check` notes a project that records a different version, so whoever inherits a project knows which rules it was built with. Bump it with every release, together with `starter/portably.config.json` and `docs/portably.config.json`.

From 1.0 the contract is stable: a change that would break an existing project waits for the next major version, and is marked **Breaking** in `CHANGELOG.md` with what a project has to do. A breaking change removes or changes the meaning of a public class or custom property, the default namespace, a token path or locked scale step, the page anatomy, supported token syntax, a finding kind or a JSON key. Additions are not breaking.

## Repository boundaries

- `foundation/` is the canonical reusable public CSS foundation.
- `starter/` is the self-contained copyable client-project scaffold.
- `AGENTS.md` is the guide for building a project from a design; `starter/AGENTS.md` is the guide every project carries. A rule for continuing work goes in the project guide, not in both.
- `standard/` defines exact Portably contracts.
- `docs/` is the published documentation site for people, built as a Portably project.
- `portably.py` is the command; `tools/` contains the code behind it.
- `tests/` contains Portably regression scripts.

Do not add a production dependency merely to make a fixture convenient. The portable deliverable remains ordinary HTML/CSS/JS/assets.
