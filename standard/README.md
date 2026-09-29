# Portably contracts

The exact rules `python portably.py check` enforces. Agents and developers start from `AGENTS.md` (in the Portably folder and in every project); come here when you need a precise rule.

| Contract | What it defines |
| --- | --- |
| [SYSTEM.md](SYSTEM.md) | the design system: required tokens, which values must come from tokens, snapping, exceptions, promotion, the token file format, contrast |
| [STRUCTURE.md](STRUCTURE.md) | project files, class-name vocabularies and the page anatomy |
| [FOUNDATION.md](FOUNDATION.md) | the shared foundation CSS, the namespace, the cascade and host integration |
| [THEMING.md](THEMING.md) | dark mode, brand variations and sections with their own colours |
| [ACCESSIBILITY.md](ACCESSIBILITY.md) | the accessibility minimum for the foundation and every interactive component |

The thresholds and lists behind them are data: `system-policy.json` (snap distances, required tokens), `spacing-scale.json`, `breakpoints.json` and `token-policy.json` (baseline tokens that may stay unused).
