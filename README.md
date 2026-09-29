<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/portably-logo-light-text.svg">
    <img src="docs/assets/portably-logo-dark-text.svg" alt="Portably" width="200">
  </picture>
</p>

<p align="center"><strong>Portably gives an AI agent a predictable system to build a design into, and leaves behind a repository that anyone can continue.</strong></p>

<p align="center"><a href="https://devygits.github.io/portably/">Documentation</a> · <a href="https://devygits.github.io/portably/pages/quickstart.html">Quickstart</a> · <a href="AGENTS.md">Guide for AI agents</a></p>

Give an agent a Figma file, screenshots, an existing site or a brief. It builds plain HTML, CSS and JavaScript on one complete design system, in a structure every Portably project shares, and verifies the result with one command. The project runs without Portably: no runtime, no frontend dependency, no build step.

## Quick start

Download Portably next to where the project will live:

```bash
git clone https://github.com/devygits/portably
```

Give your agent the design and one sentence:

> Build this design with Portably. Read `portably/AGENTS.md` first and create the project in `site/`.

Portably needs Python 3.9 or newer. The final check also opens every page in a browser, which needs Playwright: `pip install playwright`, then `playwright install chromium`.

## What's in this repository

| | |
| --- | --- |
| `AGENTS.md` | the guide an AI agent follows to build a design with Portably |
| `portably.py`, `tools/` | the command: `init`, `check`, `fix` and `promote` |
| `starter/` | what `init` copies into a new project |
| `foundation/` | the shared CSS every project carries: a scoped reset, the button and the skip link |
| `standard/` | the exact rules the check enforces |
| `docs/` | the documentation site, itself built with Portably |
| `tests/` | the regression tests |
| `DEVELOPMENT.md` | how to work on Portably itself |

## License

MIT. See [LICENSE](LICENSE). The documentation site uses the Inter typeface, under the SIL Open Font License 1.1 ([docs/assets/fonts/Inter-OFL.txt](docs/assets/fonts/Inter-OFL.txt)).
